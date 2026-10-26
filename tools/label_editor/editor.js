/* 地图标签编辑器前端: SVG 画布 + 标签状态模型 + 侧栏列表.
 *
 * 状态模型(关键, 否则刷新后位移会叠加两遍):
 *   已有标签的显示平移 = current.moved[id] - baked.moved[id]
 *   新增标注的显示平移 = current.added[key].xy - baked.added[key].xy
 * baked 是 SVG 注释里记录的"已经画进图里的布局", current 是磁盘上的布局文件.
 * 保存只写布局文件; 用户重跑脚本后 baked 追上 current, 平移自然归零.
 * 完整说明见 docs/label-editing.md.
 */
'use strict';

(() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const LABEL_PREFIX = 'label-';
  const MIN_SCALE = 0.05;
  const MAX_SCALE = 20;
  const FIT_FILL = 0.9; // 四周各留 5% 边距
  const TEXT_TRUNCATE = 24;
  const PICK_PROMPT = '新增标注文字:';

  // 与 cartopy_file.labels 的默认样式保持一致; 从图上抄不到样式时用它兜底.
  const STYLE_DEFAULTS = {
    font_size: 10,
    color: '#000000',
    italic: false,
    weight: 'normal',
    halo_color: '#ffffff',
    halo_width: 2.5,
    anchor: 'start',
  };

  // 编辑器全局状态. DOM 元素在 cacheDom() 里补.
  const S = {
    figure: '',
    svgPath: '',
    placementsPath: '',
    renderHint: null,
    error: null,
    saveError: null,
    baked: null, // 归一化后的 baked 布局 JSON
    bakedMoved: {}, // id -> {dx,dy}
    bakedAdded: new Map(), // key -> record
    moved: {}, // id -> {dx,dy[,text]} (布局文件里的绝对值)
    added: [], // 新增标注记录数组(顺序即写盘顺序)
    addedIndex: new Map(), // key -> record
    labels: new Map(), // id -> Label
    items: new Map(), // id -> <li>
    selectedId: null,
    dirty: false,
    saveState: '正在载入…',
    saveStateKind: 'busy',
    needsRender: false,
    outline: false,
    scale: 1,
    panX: 0,
    panY: 0,
    viewBox: { x: 0, y: 0, width: 1, height: 1 },
    svgRoot: null,
    labelOverlay: null,
    selectionOverlay: null,
    spaceHeld: false,
    pickMode: false,
    fontFamily: '',
    editing: false,
    readyAt: 0,
    drag: null,
    panDrag: null,
  };

  const els = {};
  const $ = (id) => document.getElementById(id);

  // 验证与排错用: 把未捕获异常和 console.error 收进数组, 供自动化检查"打开后无 console 错误".
  // 只记录不改变行为; error 事件本身仍会照常输出到浏览器控制台.
  window.__editorErrors = [];
  window.addEventListener('error', (event) => {
    window.__editorErrors.push(String((event && event.message) || event));
  });
  window.addEventListener('unhandledrejection', (event) => {
    window.__editorErrors.push(String((event && event.reason) || event));
  });
  const nativeConsoleError = console.error.bind(console);
  console.error = (...args) => {
    window.__editorErrors.push(
      args.map((arg) => String((arg && arg.stack) || arg)).join(' ')
    );
    nativeConsoleError(...args);
  };

  // ── 启动 ──────────────────────────────────────────────────────

  boot();

  function boot() {
    cacheDom();
    bindFocusBlur();
    bindToolbar();
    bindViewport();
    bindKeyboard();
    bindUnload();
    load().catch(showFatal);
  }

  function bindFocusBlur() {
    // 画布上的 pointerdown 常被 preventDefault(为了拖动/平移), 浏览器就不会自动
    // 把焦点从"步长"输入框移走; 那样方向键会改输入框而不是微调标签. 这里主动 blur.
    document.addEventListener(
      'pointerdown',
      (event) => {
        const active = document.activeElement;
        if (
          active &&
          isTypingTarget(active) &&
          event.target !== active &&
          !(active.contains && active.contains(event.target))
        ) {
          active.blur();
        }
      },
      true
    );
  }

  function cacheDom() {
    Object.assign(els, {
      figureName: $('figure-name'),
      banner: $('banner'),
      viewport: $('viewport'),
      canvas: $('canvas'),
      hint: $('hint'),
      labelList: $('label-list'),
      labelCount: $('label-count'),
      selectionPanel: $('selection-panel'),
      selStatus: $('sel-status'),
      selText: $('sel-text'),
      selOffset: $('sel-offset'),
      selPosLabel: $('sel-pos-label'),
      selPos: $('sel-pos'),
      btnResetOne: $('btn-reset-one'),
      btnDeleteOne: $('btn-delete-one'),
      statusFigure: $('status-figure'),
      statusMoved: $('status-moved'),
      statusAdded: $('status-added'),
      statusZoom: $('status-zoom'),
      statusSave: $('status-save'),
      step: $('step'),
      styleSource: $('style-source'),
      btnAdd: $('btn-add'),
      btnSave: $('btn-save'),
      toggleOutline: $('toggle-outline'),
      toggleHighlight: $('toggle-highlight'),
    });
  }

  async function load() {
    const started = performance.now();
    const state = await fetchJson('/api/state');
    S.figure = state.figure;
    S.svgPath = state.svg_path;
    S.placementsPath = state.placements_path;
    S.renderHint = state.render_hint;
    S.error = state.error;
    S.baked = state.baked || null;
    S.bakedMoved = (S.baked && S.baked.moved) || {};
    S.bakedAdded = new Map(
      ((S.baked && S.baked.added) || []).map((record) => [record.key, record])
    );

    const current = state.current;
    S.moved = cloneMoved(current && current.moved);
    S.added = cloneAdded(current && current.added);
    rebuildAddedIndex();

    document.title = `${S.figure} · 标签编辑器`;
    els.figureName.textContent = S.figure;
    els.figureName.title = S.svgPath;

    const response = await fetch('/map.svg', { cache: 'no-store' });
    if (!response.ok) {
      throw new Error(`/map.svg 返回 HTTP ${response.status}`);
    }
    importSvg(await response.text());

    initOverlays();
    collectLabels();
    captureFontFamily();
    syncStateToDom();
    applyAllTransforms();
    rebuildList();
    fitView();

    S.needsRender = computeNeedsRender();
    S.editing = true;
    S.readyAt = performance.now();
    setSaveState('已载入', '');
    updateChrome();
    window.__editorReady = true;
    console.info(
      `[label-editor] 就绪 ${S.readyAt.toFixed(0)} ms, 标签 ${S.labels.size} 个` +
        `(底图 ${existingLabels().length}), 新增 ${S.added.length} 个`
    );
  }

  function showFatal(error) {
    console.error('[label-editor] 初始化失败', error);
    S.editing = false;
    S.saveState = '载入失败';
    S.saveStateKind = 'error';
    updateSaveState();
    const row = bannerRow('error', `编辑器初始化失败: ${error.message || error}`);
    els.banner.replaceChildren(row);
    els.banner.classList.remove('hidden');
    window.__editorReady = false;
  }

  // ── SVG 解析与标签收集 ───────────────────────────────────────

  function importSvg(text) {
    const parsed = new DOMParser().parseFromString(text, 'image/svg+xml');
    const parseError = parsed.getElementsByTagName('parsererror')[0];
    if (parseError) {
      throw new Error(
        'SVG 解析失败: ' + String(parseError.textContent || '').slice(0, 300)
      );
    }
    const root = document.importNode(parsed.documentElement, true);
    S.viewBox = readViewBox(root);
    // 让 1 个 SVG 用户单位 = 1 个 CSS px; 视图缩放只由 CSS transform 承担,
    // 这样"屏幕位移 ÷ 缩放 = SVG 用户单位(pt)"这条换算始终成立.
    root.setAttribute('width', String(S.viewBox.width));
    root.setAttribute('height', String(S.viewBox.height));
    root.style.width = `${S.viewBox.width}px`;
    root.style.height = `${S.viewBox.height}px`;
    els.canvas.appendChild(root);
    S.svgRoot = root;
  }

  function readViewBox(root) {
    const raw = (root.getAttribute('viewBox') || '').trim();
    const parts = raw.split(/[\s,]+/).map(Number);
    if (parts.length === 4 && parts.every(Number.isFinite)) {
      return { x: parts[0], y: parts[1], width: parts[2], height: parts[3] };
    }
    const width = parseFloat(root.getAttribute('width')) || 1000;
    const height = parseFloat(root.getAttribute('height')) || 1000;
    return { x: 0, y: 0, width, height };
  }

  function initOverlays() {
    S.labelOverlay = createSvg('g', { id: '__label_overlay', 'pointer-events': 'none' });
    S.selectionOverlay = createSvg('g', {
      id: '__selection_overlay',
      'pointer-events': 'none',
    });
    S.svgRoot.appendChild(S.labelOverlay);
    S.svgRoot.appendChild(S.selectionOverlay);
  }

  function collectLabels() {
    const nodes = S.svgRoot.querySelectorAll('[id^="label-"]');
    for (const el of nodes) {
      const id = el.id;
      if (!id.startsWith(LABEL_PREFIX) || S.labels.has(id)) continue;
      const textEl = el.localName === 'text' ? el : el.querySelector('text');
      if (!textEl) continue; // 没有文字的 id 前缀元素不当标签处理
      S.labels.set(id, makeLabel(el, textEl, { added: false }));
    }
  }

  function makeLabel(el, textEl, options) {
    // matplotlib 的标签组一般没有 transform; 若元素自带 transform(旋转等),
    // 在它外面套一层新的 <g>, 把编辑器位移加在包装层, 不覆盖原属性.
    let node = el;
    let baseTransform = el.getAttribute('transform');
    if (baseTransform !== null) {
      const wrapper = createSvg('g', { 'data-editor-wrapper': '1' });
      el.parentNode.insertBefore(wrapper, el);
      wrapper.appendChild(el);
      node = wrapper;
    }
    const label = {
      id: el.id,
      el,
      node,
      textEl,
      baseTransform,
      added: !!options.added,
      hidden: false,
      domX: options.domX,
      domY: options.domY,
      naturalText: normalizeSpace(textEl.textContent || ''),
    };
    attachLabelEvents(label);
    return label;
  }

  function createAddedLabel(record) {
    const group = createSvg('g', { id: record.key, 'data-editor-added': '1' });
    const text = createSvg('text', {
      x: fmt(record.x),
      y: fmt(record.y),
    });
    text.textContent = record.text;
    applyAddedStyle(text, record);
    const rotation = Number(record.rotation) || 0;
    if (rotation !== 0) {
      // SVG 的 rotate 正值顺时针, 与布局文件里的 rotation 同一约定.
      text.setAttribute(
        'transform',
        `rotate(${fmt(rotation)} ${fmt(record.x)} ${fmt(record.y)})`
      );
    }
    group.appendChild(text);
    S.svgRoot.insertBefore(group, S.labelOverlay);
    const label = makeLabel(group, text, {
      added: true,
      domX: record.x,
      domY: record.y,
    });
    return label;
  }

  function applyAddedStyle(text, record) {
    const style = normalizeStyle(record.style);
    const parts = [
      `font-size: ${fmt(style.font_size)}px`,
      `fill: ${style.color}`,
      `text-anchor: ${style.anchor}`,
    ];
    if (S.fontFamily) parts.push(`font-family: ${S.fontFamily}`);
    if (style.italic) parts.push('font-style: italic');
    if (style.weight && style.weight !== 'normal') {
      parts.push(`font-weight: ${style.weight}`);
    }
    if (style.halo_width > 0) {
      // 白描边 + paint-order: stroke 复刻 matplotlib 的 withStroke 光晕.
      parts.push(`stroke: ${style.halo_color}`);
      parts.push(`stroke-width: ${fmt(style.halo_width)}`);
      parts.push('paint-order: stroke');
    }
    text.setAttribute('style', parts.join('; '));
  }

  function attachLabelEvents(label) {
    label.el.addEventListener('pointerenter', () => setHover(label.id, true));
    label.el.addEventListener('pointerleave', () => setHover(label.id, false));
  }

  function captureFontFamily() {
    // 新增标注沿用底图已有文字的字族, 否则内嵌字体子集里没有新字形.
    for (const label of S.labels.values()) {
      const inline = label.textEl.style && label.textEl.style.fontFamily;
      if (inline) {
        S.fontFamily = inline;
        return;
      }
    }
    const firstText = S.labels.size
      ? [...S.labels.values()][0].textEl
      : S.svgRoot.querySelector('text');
    if (firstText) {
      S.fontFamily = getComputedStyle(firstText).fontFamily || '';
    }
  }

  // ── 状态 ↔ DOM 同步 ──────────────────────────────────────────

  function syncStateToDom() {
    // 1. baked 里画出来的新增标注: 标记成"新增", 锚点用 baked 记录.
    for (const [key, record] of S.bakedAdded) {
      const label = S.labels.get(key);
      if (!label) continue;
      label.added = true;
      label.domX = Number(record.x);
      label.domY = Number(record.y);
    }
    // 2. current.added: DOM 里已有(烤过)的复用, 没有的补画.
    for (const record of S.added) {
      let label = S.labels.get(record.key);
      if (!label) {
        label = createAddedLabel(record);
        S.labels.set(record.key, label);
        continue;
      }
      label.added = true;
      if (label.domX === undefined) {
        // 布局里有、SVG 却没有 marker 时(手工删过标记), 用 DOM 里的坐标当基准,
        // 先让位移为 0, 不凭空把标签再挪一次.
        label.domX = readCoord(label.textEl.getAttribute('x'), record.x);
        label.domY = readCoord(label.textEl.getAttribute('y'), record.y);
      }
    }
    // 3. baked 有、current 没有: 用户在别处删掉了, 先隐藏.
    for (const key of S.bakedAdded.keys()) {
      if (S.addedIndex.has(key)) continue;
      const label = S.labels.get(key);
      if (label) hideLabel(label);
    }
  }

  function applyAllTransforms() {
    for (const label of S.labels.values()) {
      if (label.hidden) continue;
      refreshLabelTransform(label);
    }
  }

  function refreshLabelTransform(label) {
    if (label.added) {
      const record = S.addedIndex.get(label.id);
      if (!record) {
        hideLabel(label);
        return;
      }
      const baseX = label.domX === undefined ? record.x : label.domX;
      const baseY = label.domY === undefined ? record.y : label.domY;
      setTranslate(label, round3(record.x - baseX), round3(record.y - baseY));
      return;
    }
    const offset = currentOffset(label.id);
    setTranslate(label, offset.dx, offset.dy);
  }

  function setTranslate(label, dx, dy) {
    label.node.setAttribute('transform', `translate(${fmt(dx)} ${fmt(dy)})`);
  }

  function hideLabel(label) {
    label.hidden = true;
    label.el.style.display = 'none';
    label.el.classList.remove('is-hover', 'is-selected');
    const item = S.items.get(label.id);
    if (item) item.classList.remove('is-hover', 'is-selected');
  }

  function currentOffset(id) {
    const record = S.moved[id];
    const baked = S.bakedMoved[id] || { dx: 0, dy: 0 };
    const dx = (record ? Number(record.dx) : 0) - Number(baked.dx || 0);
    const dy = (record ? Number(record.dy) : 0) - Number(baked.dy || 0);
    return { dx: round3(dx), dy: round3(dy) };
  }

  function addedOffset(record, label) {
    const baseX = label.domX === undefined ? record.x : label.domX;
    const baseY = label.domY === undefined ? record.y : label.domY;
    return { dx: round3(record.x - baseX), dy: round3(record.y - baseY) };
  }

  function writeExistingOffset(id, offsetX, offsetY) {
    const baked = S.bakedMoved[id] || { dx: 0, dy: 0 };
    const previous = S.moved[id] || {};
    S.moved[id] = {
      ...previous,
      dx: round3(Number(baked.dx || 0) + offsetX),
      dy: round3(Number(baked.dy || 0) + offsetY),
    };
  }

  // ── 视图(平移/缩放) ─────────────────────────────────────────

  function fitView() {
    const width = els.canvas.clientWidth;
    const height = els.canvas.clientHeight;
    if (!width || !height) return;
    const vb = S.viewBox;
    const scale = clamp(
      Math.min((width * FIT_FILL) / vb.width, (height * FIT_FILL) / vb.height),
      MIN_SCALE,
      MAX_SCALE
    );
    S.scale = scale;
    S.panX = (width - scale * vb.width) / 2 - scale * vb.x;
    S.panY = (height - scale * vb.height) / 2 - scale * vb.y;
    applyView();
  }

  function applyView() {
    if (!S.svgRoot) return;
    S.svgRoot.style.transform =
      `translate(${fmt(S.panX)}px, ${fmt(S.panY)}px) scale(${fmt(S.scale)})`;
    els.statusZoom.textContent = `缩放 ${Math.round(S.scale * 100)}%`;
    if (S.outline) updateOutlines();
  }

  function zoomAt(screenX, screenY, factor) {
    const next = clamp(S.scale * factor, MIN_SCALE, MAX_SCALE);
    if (Math.abs(next - S.scale) < 1e-9) return;
    const userX = (screenX - S.panX) / S.scale;
    const userY = (screenY - S.panY) / S.scale;
    S.scale = next;
    S.panX = screenX - next * userX;
    S.panY = screenY - next * userY;
    applyView();
  }

  function zoomTo(targetScale) {
    const next = clamp(targetScale, MIN_SCALE, MAX_SCALE);
    const width = els.canvas.clientWidth;
    const height = els.canvas.clientHeight;
    zoomAt(width / 2, height / 2, next / S.scale);
  }

  function screenToUser(clientX, clientY) {
    const rect = els.canvas.getBoundingClientRect();
    return {
      x: (clientX - rect.left - S.panX) / S.scale,
      y: (clientY - rect.top - S.panY) / S.scale,
    };
  }

  function userToClient(userX, userY) {
    const rect = els.canvas.getBoundingClientRect();
    return {
      x: rect.left + S.panX + S.scale * userX,
      y: rect.top + S.panY + S.scale * userY,
    };
  }

  // 计算元素在 SVG 用户坐标里的外接矩形. 优先 getBBox+getCTM(含旋转与祖先变换),
  // 失败时用屏幕矩形反算, 保证叠加框不会因渲染器差异而消失.
  function elementUserRect(el) {
    try {
      if (typeof el.getBBox === 'function') {
        const box = el.getBBox();
        const matrix = typeof el.getCTM === 'function' ? el.getCTM() : null;
        if (matrix && (box.width || box.height)) {
          const corners = [
            [box.x, box.y],
            [box.x + box.width, box.y],
            [box.x, box.y + box.height],
            [box.x + box.width, box.y + box.height],
          ].map(([x, y]) => applyMatrix(matrix, x, y));
          return boundsOf(corners);
        }
      }
    } catch (error) {
      /* 某些渲染器下 getBBox 可能抛错, 走下面的屏幕矩形兜底. */
    }
    const screen = el.getBoundingClientRect();
    const canvasRect = els.canvas.getBoundingClientRect();
    if (!screen.width && !screen.height) return null;
    const x1 = (screen.left - canvasRect.left - S.panX) / S.scale;
    const y1 = (screen.top - canvasRect.top - S.panY) / S.scale;
    const x2 = (screen.right - canvasRect.left - S.panX) / S.scale;
    const y2 = (screen.bottom - canvasRect.top - S.panY) / S.scale;
    return { x: x1, y: y1, width: x2 - x1, height: y2 - y1 };
  }

  function centerOnLabel(id) {
    const label = S.labels.get(id);
    if (!label || label.hidden) return;
    const rect = elementUserRect(label.el);
    if (!rect) return;
    const width = els.canvas.clientWidth;
    const height = els.canvas.clientHeight;
    S.panX = width / 2 - S.scale * (rect.x + rect.width / 2);
    S.panY = height / 2 - S.scale * (rect.y + rect.height / 2);
    applyView();
  }

  // ── 选中 / 侧栏 ────────────────────────────────────────────

  function existingLabels() {
    return [...S.labels.values()].filter((label) => !label.added && !label.hidden);
  }

  function visibleLabels() {
    return [...S.labels.values()].filter((label) => !label.hidden);
  }

  function labelStatus(label) {
    if (label.added) return 'added';
    if (S.moved[label.id]) return 'moved';
    const offset = currentOffset(label.id);
    if (Math.abs(offset.dx) > 1e-9 || Math.abs(offset.dy) > 1e-9) return 'moved';
    return 'default';
  }

  function displayText(label, max = TEXT_TRUNCATE) {
    const text = normalizeSpace(label.naturalText || '');
    if (!text) return '(无文字)';
    const chars = [...text];
    return chars.length > max ? `${chars.slice(0, max).join('')}…` : text;
  }

  function selectLabel(id, options = {}) {
    const label = S.labels.get(id);
    if (!label || label.hidden) return;
    S.selectedId = id;
    for (const item of S.labels.values()) {
      item.el.classList.toggle('is-selected', item.id === id);
    }
    updateAllItems();
    updateSelectionPanel();
    updateSelectionOverlay();
    if (options.center) {
      centerOnLabel(id);
      const item = S.items.get(id);
      if (item) item.scrollIntoView({ block: 'nearest' });
    }
  }

  function deselect() {
    S.selectedId = null;
    for (const label of S.labels.values()) {
      label.el.classList.remove('is-selected');
    }
    updateAllItems();
    updateSelectionPanel();
    updateSelectionOverlay();
  }

  function setHover(id, on) {
    const label = S.labels.get(id);
    if (!label) return;
    label.el.classList.toggle('is-hover', !!on);
    const item = S.items.get(id);
    if (item) item.classList.toggle('is-hover', !!on);
  }

  function rebuildList() {
    els.labelList.replaceChildren();
    S.items.clear();
    for (const label of visibleLabels()) {
      const item = document.createElement('li');
      item.className = 'label-item';
      item.dataset.id = label.id;
      const text = document.createElement('span');
      text.className = 'label-text';
      text.textContent = displayText(label);
      text.title = normalizeSpace(label.naturalText || '');
      const status = document.createElement('span');
      status.className = 'label-status';
      item.append(text, status);
      item.addEventListener('click', () => selectLabel(label.id, { center: true }));
      item.addEventListener('pointerenter', () => setHover(label.id, true));
      item.addEventListener('pointerleave', () => setHover(label.id, false));
      els.labelList.appendChild(item);
      S.items.set(label.id, item);
      updateItem(label.id);
    }
    els.labelCount.textContent = String(S.items.size);
    rebuildStyleSourceOptions();
  }

  function rebuildStyleSourceOptions() {
    // "样式"下拉框决定新增标注抄谁的样式; 默认空值 = 跟随当前选中标签.
    const select = els.styleSource;
    if (!select) return;
    const previous = select.value;
    const options = [createOption('', '跟随选中')];
    for (const label of visibleLabels()) {
      options.push(createOption(label.id, displayText(label, 18)));
    }
    select.replaceChildren(...options);
    if ([...select.options].some((option) => option.value === previous)) {
      select.value = previous;
    }
  }

  function createOption(value, text) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = text;
    return option;
  }

  function updateItem(id) {
    const item = S.items.get(id);
    const label = S.labels.get(id);
    if (!item || !label) return;
    item.classList.toggle('is-selected', S.selectedId === id);
    const status = item.querySelector('.label-status');
    const kind = labelStatus(label);
    status.textContent = kind === 'added' ? '新增' : kind === 'moved' ? '已移动' : '默认';
    status.className =
      'label-status' +
      (kind === 'added' ? ' status-added' : kind === 'moved' ? ' status-moved' : '');
  }

  function updateAllItems() {
    for (const id of S.items.keys()) updateItem(id);
  }

  function updateSelectionPanel() {
    const id = S.selectedId;
    const label = id ? S.labels.get(id) : null;
    if (!label || label.hidden) {
      els.selectionPanel.classList.add('hidden');
      return;
    }
    els.selectionPanel.classList.remove('hidden');
    els.selText.textContent = displayText(label, 80);
    const kind = labelStatus(label);
    els.selStatus.textContent =
      kind === 'added' ? '新增' : kind === 'moved' ? '已移动' : '默认';
    els.selStatus.className =
      'badge' +
      (kind === 'added' ? ' badge-added' : kind === 'moved' ? ' badge-moved' : '');

    if (label.added) {
      const record = S.addedIndex.get(id);
      if (record) {
        const offset = addedOffset(record, label);
        els.selOffset.textContent = `${signed(offset.dx)}, ${signed(offset.dy)} pt`;
        els.selPosLabel.classList.remove('hidden');
        els.selPos.classList.remove('hidden');
        els.selPos.textContent = `${record.x.toFixed(2)}, ${record.y.toFixed(2)}`;
      }
      els.btnResetOne.classList.add('hidden');
      els.btnDeleteOne.classList.remove('hidden');
    } else {
      const offset = currentOffset(id);
      els.selOffset.textContent = `${signed(offset.dx)}, ${signed(offset.dy)} pt`;
      els.selPosLabel.classList.add('hidden');
      els.selPos.classList.add('hidden');
      els.btnResetOne.classList.remove('hidden');
      els.btnDeleteOne.classList.add('hidden');
    }
  }

  function updateSelectionOverlay() {
    if (!S.selectionOverlay) return;
    S.selectionOverlay.replaceChildren();
    const id = S.selectedId;
    if (!id) return;
    const label = S.labels.get(id);
    if (!label || label.hidden) return;
    const rect = elementUserRect(label.el);
    if (!rect) return;
    const pad = 3;
    const outline = createSvg('rect', {
      x: fmt(rect.x - pad),
      y: fmt(rect.y - pad),
      width: fmt(rect.width + pad * 2),
      height: fmt(rect.height + pad * 2),
      class: 'selection-outline',
    });
    S.selectionOverlay.appendChild(outline);
  }

  function updateOutlines() {
    if (!S.labelOverlay) return;
    S.labelOverlay.replaceChildren();
    if (!S.outline) return;
    for (const label of visibleLabels()) {
      const rect = elementUserRect(label.el);
      if (!rect) continue;
      S.labelOverlay.appendChild(
        createSvg('rect', {
          x: fmt(rect.x),
          y: fmt(rect.y),
          width: fmt(rect.width),
          height: fmt(rect.height),
          class: 'label-outline',
        })
      );
    }
  }

  // ── 拖动 / 平移 / 缩放 ──────────────────────────────────────

  function bindViewport() {
    els.viewport.addEventListener('pointerdown', onPointerDown);
    els.viewport.addEventListener('pointermove', onPointerMove);
    els.viewport.addEventListener('pointerup', onPointerUp);
    els.viewport.addEventListener('pointercancel', onPointerUp);
    els.viewport.addEventListener('wheel', onWheel, { passive: false });
    els.viewport.addEventListener('dblclick', onDoubleClick);
    els.viewport.addEventListener('auxclick', (event) => event.preventDefault());
    els.viewport.addEventListener('mousedown', (event) => {
      if (event.button === 1) event.preventDefault(); // 中键: 只要平移, 不要自动滚动
    });
    els.viewport.addEventListener('contextmenu', (event) => {
      if (S.pickMode) event.preventDefault();
    });
    els.viewport.addEventListener('dragstart', (event) => event.preventDefault());
  }

  function onPointerDown(event) {
    if (!S.editing || event.button === 2) return;
    if (S.pickMode && event.button === 0) {
      event.preventDefault();
      const user = screenToUser(event.clientX, event.clientY);
      placeAnnotation(user.x, user.y);
      return;
    }
    if (event.button === 1 || (event.button === 0 && S.spaceHeld)) {
      beginPan(event);
      return;
    }
    if (event.button !== 0) return;

    const hit =
      event.target && event.target.closest
        ? event.target.closest('[id^="label-"]')
        : null;
    if (hit && S.labels.has(hit.id) && !S.labels.get(hit.id).hidden) {
      beginDrag(event, hit.id);
      return;
    }
    beginPan(event);
  }

  function beginPan(event) {
    event.preventDefault();
    S.panDrag = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      panX: S.panX,
      panY: S.panY,
      moved: false,
    };
    els.viewport.setPointerCapture(event.pointerId);
    els.viewport.classList.add('is-panning');
  }

  function beginDrag(event, id) {
    event.preventDefault();
    const label = S.labels.get(id);
    if (!label) return;
    selectLabel(id);
    let baseOffset;
    let baseX = 0;
    let baseY = 0;
    if (label.added) {
      const record = S.addedIndex.get(id);
      if (!record) return;
      baseOffset = addedOffset(record, label);
      baseX = Number(record.x);
      baseY = Number(record.y);
    } else {
      baseOffset = currentOffset(id);
    }
    S.drag = {
      pointerId: event.pointerId,
      id,
      startX: event.clientX,
      startY: event.clientY,
      moved: false,
      added: label.added,
      baseOffset,
      baseX,
      baseY,
    };
    els.viewport.setPointerCapture(event.pointerId);
    els.viewport.classList.add('is-dragging');
    label.el.classList.add('is-dragging');
    setHover(id, false);
  }

  function onPointerMove(event) {
    if (S.drag && event.pointerId === S.drag.pointerId) {
      const dxScreen = event.clientX - S.drag.startX;
      const dyScreen = event.clientY - S.drag.startY;
      if (Math.abs(dxScreen) > 0.5 || Math.abs(dyScreen) > 0.5) {
        S.drag.moved = true;
      }
      const dx = dxScreen / S.scale;
      const dy = dyScreen / S.scale;
      const label = S.labels.get(S.drag.id);
      if (!label) return;
      if (S.drag.added) {
        const record = S.addedIndex.get(S.drag.id);
        if (!record) return;
        record.x = round3(S.drag.baseX + dx);
        record.y = round3(S.drag.baseY + dy);
      } else {
        writeExistingOffset(
          S.drag.id,
          S.drag.baseOffset.dx + dx,
          S.drag.baseOffset.dy + dy
        );
      }
      refreshLabelTransform(label);
      updateSelectionOverlay();
      updateSelectionPanel();
      updateItem(S.drag.id);
      updateCounts();
      return;
    }
    if (S.panDrag && event.pointerId === S.panDrag.pointerId) {
      const dx = event.clientX - S.panDrag.startX;
      const dy = event.clientY - S.panDrag.startY;
      if (Math.abs(dx) > 1 || Math.abs(dy) > 1) S.panDrag.moved = true;
      S.panX = S.panDrag.panX + dx;
      S.panY = S.panDrag.panY + dy;
      applyView();
    }
  }

  function onPointerUp(event) {
    if (S.drag && event.pointerId === S.drag.pointerId) {
      const drag = S.drag;
      S.drag = null;
      els.viewport.classList.remove('is-dragging');
      const label = S.labels.get(drag.id);
      if (label) {
        label.el.classList.remove('is-dragging');
        // 拖回原地时清掉没有必要的 {0,0} 记录, 保持布局文件干净;
        // baked 非 0 时不能删, 否则显示位置会跳回脚本默认位置.
        if (!drag.added) {
          const baked = S.bakedMoved[drag.id] || { dx: 0, dy: 0 };
          const offset = currentOffset(drag.id);
          const atZero = Math.abs(offset.dx) < 5e-4 && Math.abs(offset.dy) < 5e-4;
          const bakedZero =
            Math.abs(Number(baked.dx || 0)) < 5e-4 &&
            Math.abs(Number(baked.dy || 0)) < 5e-4;
          if (atZero && bakedZero && !(S.moved[drag.id] || {}).text) {
            delete S.moved[drag.id];
            refreshLabelTransform(label);
          }
        }
      }
      if (drag.moved) markDirty();
      updateSelectionOverlay();
      updateSelectionPanel();
      updateItem(drag.id);
      updateCounts();
      updateChrome();
      return;
    }
    if (S.panDrag && event.pointerId === S.panDrag.pointerId) {
      const drag = S.panDrag;
      S.panDrag = null;
      els.viewport.classList.remove('is-panning');
      if (!drag.moved && !S.pickMode) deselect();
    }
  }

  function onWheel(event) {
    if (!S.editing) return;
    event.preventDefault();
    const rect = els.canvas.getBoundingClientRect();
    const delta = event.deltaY * (event.deltaMode === 1 ? 16 : 1);
    const factor = Math.exp(-delta * 0.0015);
    zoomAt(event.clientX - rect.left, event.clientY - rect.top, factor);
  }

  function onDoubleClick(event) {
    if (event.target.closest && event.target.closest('[id^="label-"]')) return;
    fitView();
  }

  // ── 工具栏 / 键盘 ──────────────────────────────────────────

  function bindToolbar() {
    $('btn-fit').addEventListener('click', fitView);
    $('btn-zoom-100').addEventListener('click', () => zoomTo(1));
    $('btn-zoom-in').addEventListener('click', () => zoomTo(S.scale * 1.25));
    $('btn-zoom-out').addEventListener('click', () => zoomTo(S.scale / 1.25));
    $('btn-add').addEventListener('click', togglePick);
    $('btn-save').addEventListener('click', save);
    $('btn-reset-all').addEventListener('click', resetAll);
    els.step.addEventListener('change', () => {
      const value = parseFloat(els.step.value);
      if (!Number.isFinite(value) || value <= 0) els.step.value = '1.0';
    });
    els.toggleOutline.addEventListener('change', () => {
      S.outline = els.toggleOutline.checked;
      updateOutlines();
    });
    els.toggleHighlight.addEventListener('change', () => {
      els.canvas.classList.toggle(
        'highlight-labels',
        els.toggleHighlight.checked
      );
    });
    els.btnResetOne.addEventListener('click', resetSelected);
    els.btnDeleteOne.addEventListener('click', deleteSelectedAdded);
  }

  function bindKeyboard() {
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
  }

  function onKeyDown(event) {
    const key = event.key;
    if ((event.ctrlKey || event.metaKey) && key.toLowerCase() === 's') {
      event.preventDefault();
      save();
      return;
    }
    if (isTypingTarget(event.target)) {
      if (key === 'Escape') event.target.blur();
      return;
    }
    if (key === ' ') {
      if (isButtonTarget(event.target)) return;
      event.preventDefault();
      if (!event.repeat) {
        S.spaceHeld = true;
        els.viewport.style.cursor = 'grab';
      }
      return;
    }
    if (key === 'Escape') {
      if (S.pickMode) {
        exitPick();
      } else if (S.selectedId) {
        deselect();
      }
      return;
    }
    if ((key === 'n' || key === 'N') && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      togglePick();
      return;
    }
    if (key === 'Delete') {
      if (S.selectedId) {
        event.preventDefault();
        deleteSelectedAdded();
      }
      return;
    }
    const nudgeMap = {
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
      ArrowUp: [0, -1],
      ArrowDown: [0, 1],
    };
    if (nudgeMap[key] && S.selectedId) {
      event.preventDefault();
      nudge(nudgeMap[key][0], nudgeMap[key][1], event.shiftKey, event.altKey);
    }
  }

  function onKeyUp(event) {
    if (event.key === ' ' && S.spaceHeld) {
      S.spaceHeld = false;
      els.viewport.style.cursor = '';
    }
  }

  function nudge(directionX, directionY, shift, alt) {
    const id = S.selectedId;
    const label = id ? S.labels.get(id) : null;
    if (!label || label.hidden) return;
    const amount = stepValue() * (shift ? 10 : 1) * (alt ? 0.1 : 1);
    const dx = directionX * amount;
    const dy = directionY * amount;
    if (label.added) {
      const record = S.addedIndex.get(id);
      if (!record) return;
      record.x = round3(record.x + dx);
      record.y = round3(record.y + dy);
    } else {
      const offset = currentOffset(id);
      writeExistingOffset(id, offset.dx + dx, offset.dy + dy);
    }
    refreshLabelTransform(label);
    updateSelectionOverlay();
    updateSelectionPanel();
    updateItem(id);
    updateCounts();
    markDirty();
  }

  function stepValue() {
    const value = parseFloat(els.step.value);
    return Number.isFinite(value) && value > 0 ? value : 1;
  }

  // ── 新增标注 ────────────────────────────────────────────────

  function togglePick() {
    if (S.pickMode) exitPick();
    else beginPick();
  }

  function beginPick() {
    S.pickMode = true;
    els.viewport.classList.add('is-picking');
    els.btnAdd.classList.add('active');
    els.hint.textContent = '点击地图放置新标注 · Esc 取消';
    els.hint.classList.remove('hidden');
  }

  function exitPick() {
    S.pickMode = false;
    els.viewport.classList.remove('is-picking');
    els.btnAdd.classList.remove('active');
    els.hint.classList.add('hidden');
  }

  function placeAnnotation(userX, userY) {
    exitPick();
    const input = window.prompt(PICK_PROMPT, '');
    if (input === null) return;
    const text = input.trim();
    if (!text) return;
    addAnnotation(text, userX, userY);
  }

  function addAnnotation(text, userX, userY) {
    const { style, rotation } = cloneStyleFromSelection();
    const record = {
      key: nextCustomKey(),
      text,
      x: round3(userX),
      y: round3(userY),
      rotation: round3(rotation),
      style: normalizeStyle(style),
    };
    S.added.push(record);
    rebuildAddedIndex();
    const label = createAddedLabel(record);
    S.labels.set(record.key, label);
    refreshLabelTransform(label);
    rebuildList();
    selectLabel(record.key);
    markDirty();
    updateCounts();
    if (S.outline) updateOutlines();
    return record;
  }

  function nextCustomKey() {
    const used = new Set([...S.labels.keys(), ...S.added.map((r) => r.key)]);
    if (S.baked) for (const record of S.baked.added || []) used.add(record.key);
    let max = 0;
    for (const id of used) {
      const match = /^label-custom-(\d+)$/.exec(id);
      if (match) max = Math.max(max, parseInt(match[1], 10));
    }
    return `label-custom-${max + 1}`;
  }

  function cloneStyleFromSelection() {
    const preferred = els.styleSource ? els.styleSource.value : '';
    if (preferred) {
      const source = S.labels.get(preferred);
      if (source && !source.hidden) {
        if (source.added) {
          const record = S.addedIndex.get(source.id);
          if (record) {
            return {
              style: normalizeStyle(record.style),
              rotation: Number(record.rotation) || 0,
            };
          }
        } else {
          return styleFromTextElement(source.textEl);
        }
      }
    }
    let reference = S.selectedId ? S.labels.get(S.selectedId) : null;
    if (reference && (reference.hidden || reference.added)) {
      const record = S.addedIndex.get(reference.id);
      if (record) {
        return {
          style: normalizeStyle(record.style),
          rotation: Number(record.rotation) || 0,
        };
      }
      reference = null;
    }
    if (!reference || reference.hidden) {
      reference = existingLabels()[0] || visibleLabels()[0] || null;
    }
    if (!reference) {
      return { style: { ...STYLE_DEFAULTS }, rotation: 0 };
    }
    return styleFromTextElement(reference.textEl);
  }

  function styleFromTextElement(textEl) {
    const computed = getComputedStyle(textEl);
    const inline = textEl.style || {};
    const fontRaw =
      parseFloat(inline.fontSize) || parseFloat(computed.fontSize) || STYLE_DEFAULTS.font_size;
    const color = toCssColor(inline.fill || computed.fill, STYLE_DEFAULTS.color);
    const italic = (inline.fontStyle || computed.fontStyle) === 'italic';
    const weight = weightName(inline.fontWeight || computed.fontWeight);
    const strokeRaw = inline.stroke || computed.stroke;
    const strokeWidth = parseFloat(inline.strokeWidth || computed.strokeWidth);
    const hasHalo =
      strokeRaw && strokeRaw !== 'none' && Number.isFinite(strokeWidth) && strokeWidth > 0;
    const anchorRaw =
      inline.textAnchor || textEl.getAttribute('text-anchor') || computed.textAnchor || 'start';
    const anchor = ['start', 'middle', 'end'].includes(anchorRaw) ? anchorRaw : 'start';
    return {
      style: {
        font_size: round3(fontRaw),
        color,
        italic,
        weight,
        halo_color: hasHalo ? toCssColor(strokeRaw, '#ffffff') : STYLE_DEFAULTS.halo_color,
        halo_width: hasHalo ? round3(strokeWidth) : 0,
        anchor,
      },
      rotation: normalizeAngle(parseRotation(textEl)),
    };
  }

  function parseRotation(element) {
    const sources = [element.getAttribute('transform') || '', (element.style && element.style.transform) || ''];
    for (const source of sources) {
      const match = /rotate\(\s*(-?(?:\d+\.?\d*|\.\d+))/i.exec(source);
      if (match) return parseFloat(match[1]) || 0;
    }
    return 0;
  }

  // ── 重置 / 删除 ─────────────────────────────────────────────

  function resetSelected() {
    const id = S.selectedId;
    const label = id ? S.labels.get(id) : null;
    if (!label || label.hidden || label.added) return;
    delete S.moved[id];
    refreshLabelTransform(label);
    updateItem(id);
    updateSelectionPanel();
    updateSelectionOverlay();
    updateCounts();
    markDirty();
    if (S.outline) updateOutlines();
  }

  function deleteSelectedAdded() {
    const id = S.selectedId;
    const label = id ? S.labels.get(id) : null;
    if (!label || !label.added) return;
    const index = S.added.findIndex((record) => record.key === id);
    if (index >= 0) S.added.splice(index, 1);
    rebuildAddedIndex();
    hideLabel(label);
    S.selectedId = null;
    for (const item of S.labels.values()) item.el.classList.remove('is-selected');
    rebuildList();
    updateSelectionPanel();
    updateSelectionOverlay();
    updateCounts();
    markDirty();
    if (S.outline) updateOutlines();
  }

  function resetAll() {
    if (!window.confirm('确定清除所有标签位移与新增标注吗? 保存前不落盘.')) return;
    S.moved = {};
    S.added = [];
    rebuildAddedIndex();
    for (const label of S.labels.values()) {
      if (label.added) {
        hideLabel(label);
      } else {
        label.hidden = false;
        label.el.style.display = '';
        refreshLabelTransform(label);
      }
    }
    if (S.selectedId) {
      const selected = S.labels.get(S.selectedId);
      if (!selected || selected.hidden) S.selectedId = null;
    }
    for (const label of S.labels.values()) label.el.classList.remove('is-selected');
    rebuildList();
    updateSelectionPanel();
    updateSelectionOverlay();
    updateCounts();
    markDirty();
    if (S.outline) updateOutlines();
  }

  // ── 保存 ────────────────────────────────────────────────────

  let saving = false;

  async function save() {
    if (saving || !S.editing) return;
    saving = true;
    els.btnSave.disabled = true;
    S.saveError = null;
    setSaveState('保存中…', 'busy');
    try {
      const response = await fetch('/api/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ moved: S.moved, added: S.added }),
      });
      let data = {};
      try {
        data = await response.json();
      } catch (error) {
        data = {};
      }
      if (!response.ok) {
        throw new Error(data.error || `HTTP ${response.status}`);
      }
      S.dirty = false;
      // 保存成功即覆盖掉损坏的布局文件, 旧的 error 提示不该继续留着.
      S.error = null;
      setSaveState('已保存', 'ok');
      S.needsRender = computeNeedsRender();
      updateAllItems();
      updateCounts();
      updateBanner();
      console.info(
        `[label-editor] 已保存: ${data.path} (moved=${data.moved}, added=${data.added})`
      );
    } catch (error) {
      console.error('[label-editor] 保存失败', error);
      S.saveError = `保存失败: ${error.message || error}`;
      setSaveState('保存失败', 'error');
      updateBanner();
    } finally {
      saving = false;
      els.btnSave.disabled = false;
    }
  }

  function markDirty() {
    S.dirty = true;
    if (S.saveStateKind !== 'error') setSaveState('未保存', 'dirty');
    updateBanner();
  }

  function setSaveState(text, kind) {
    S.saveState = text;
    S.saveStateKind = kind || '';
    updateSaveState();
  }

  function updateSaveState() {
    els.statusSave.textContent = S.saveState;
    els.statusSave.className = `status-item status-save ${saveClass(S.saveStateKind)}`;
  }

  function saveClass(kind) {
    if (kind === 'dirty') return 'is-dirty';
    if (kind === 'ok') return 'is-ok';
    if (kind === 'error') return 'is-error';
    if (kind === 'busy') return 'is-busy';
    return '';
  }

  // ── 状态比较 / 顶栏 / 提示条 ────────────────────────────────

  function canonicalAdded(records) {
    return records
      .map((record) => ({
        key: record.key,
        text: record.text,
        x: round3(record.x),
        y: round3(record.y),
        rotation: round3(record.rotation || 0),
        style: canonicalStyle(record.style),
      }))
      .sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
  }

  function canonicalStyle(style) {
    const merged = normalizeStyle(style);
    return {
      font_size: round3(merged.font_size),
      color: merged.color,
      italic: !!merged.italic,
      weight: merged.weight,
      halo_color: merged.halo_color,
      halo_width: round3(merged.halo_width),
      anchor: merged.anchor,
    };
  }

  function canonicalMoved(moved) {
    const result = {};
    for (const key of Object.keys(moved || {}).sort()) {
      const record = moved[key];
      const entry = { dx: round3(record.dx), dy: round3(record.dy) };
      if (record.text) entry.text = record.text;
      result[key] = entry;
    }
    return result;
  }

  function canonicalStateDoc() {
    return {
      moved: canonicalMoved(S.moved),
      added: canonicalAdded(S.added),
    };
  }

  function canonicalBakedDoc() {
    if (!S.baked) return null;
    return {
      moved: canonicalMoved(S.baked.moved || {}),
      added: canonicalAdded(S.baked.added || []),
    };
  }

  function documentEmpty(document) {
    return (
      !document ||
      (Object.keys(document.moved || {}).length === 0 &&
        (document.added || []).length === 0)
    );
  }

  function computeNeedsRender() {
    const current = canonicalStateDoc();
    const baked = canonicalBakedDoc();
    if (documentEmpty(current) && documentEmpty(baked)) return false;
    return JSON.stringify(current) !== JSON.stringify(baked);
  }

  function updateChrome() {
    els.statusFigure.textContent = S.figure || '-';
    updateCounts();
    updateSaveState();
    updateBanner();
    els.statusZoom.textContent = `缩放 ${Math.round(S.scale * 100)}%`;
  }

  function updateCounts() {
    els.statusMoved.textContent = `已移动 ${Object.keys(S.moved).length}`;
    els.statusAdded.textContent = `新增 ${S.added.length}`;
    els.labelCount.textContent = String(visibleLabels().length);
  }

  function updateBanner() {
    const rows = [];
    if (S.error) {
      const row = bannerRow('error', S.error);
      if (S.placementsPath) {
        const path = document.createElement('span');
        path.className = 'cmd';
        path.textContent = S.placementsPath;
        row.appendChild(path);
      }
      rows.push(row);
    }
    if (S.saveError) {
      rows.push(bannerRow('error', S.saveError));
    }
    if (S.needsRender) {
      const row = bannerRow('warn', '已保存, 需要重跑脚本生成最终 SVG');
      if (S.renderHint) {
        const code = document.createElement('code');
        code.className = 'cmd';
        code.textContent = S.renderHint;
        code.title = '点击复制';
        code.addEventListener('click', () => copyToClipboard(S.renderHint));
        row.appendChild(code);
      } else {
        const note = document.createElement('span');
        note.className = 'muted';
        note.textContent = '未找到唯一引用该 SVG 的绘图脚本, 请手动重跑对应脚本';
        row.appendChild(note);
      }
      rows.push(row);
    }
    els.banner.replaceChildren(...rows);
    els.banner.classList.toggle('hidden', rows.length === 0);
  }

  function bannerRow(kind, text) {
    const row = document.createElement('div');
    row.className = `banner-row ${kind}`;
    const label = document.createElement('span');
    label.textContent = text;
    row.appendChild(label);
    return row;
  }

  function copyToClipboard(text) {
    const done = () => flashSaveState('已复制命令', 'ok');
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, () => fallbackCopy(text, done));
    } else {
      fallbackCopy(text, done);
    }
  }

  function fallbackCopy(text, done) {
    const area = document.createElement('textarea');
    area.value = text;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand('copy');
      done();
    } catch (error) {
      /* 复制失败不提示, 用户可以手动选中命令. */
    } finally {
      area.remove();
    }
  }

  let flashTimer = 0;

  function flashSaveState(text, kind) {
    els.statusSave.textContent = text;
    els.statusSave.className = `status-item status-save ${saveClass(kind)}`;
    clearTimeout(flashTimer);
    flashTimer = setTimeout(updateSaveState, 1600);
  }

  // ── 小工具 ─────────────────────────────────────────────────

  function bindUnload() {
    // 只在有未保存改动时拦截关闭/刷新; 保存后 dirty=false, 浏览器不会弹确认.
    window.addEventListener('beforeunload', (event) => {
      if (!S.dirty) return;
      event.preventDefault();
      event.returnValue = '';
    });
  }

  function cloneMoved(moved) {
    const result = {};
    for (const [key, record] of Object.entries(moved || {})) {
      result[key] = { ...record };
    }
    return result;
  }

  function cloneAdded(added) {
    return (added || []).map((record) => ({
      ...record,
      style: { ...(record.style || {}) },
    }));
  }

  function rebuildAddedIndex() {
    S.addedIndex = new Map(S.added.map((record) => [record.key, record]));
  }

  function normalizeStyle(style) {
    const merged = { ...STYLE_DEFAULTS, ...(style || {}) };
    return {
      font_size: Number(merged.font_size) || STYLE_DEFAULTS.font_size,
      color: String(merged.color || STYLE_DEFAULTS.color),
      italic: !!merged.italic,
      weight: String(merged.weight || 'normal'),
      halo_color: String(merged.halo_color || STYLE_DEFAULTS.halo_color),
      halo_width: Number.isFinite(Number(merged.halo_width))
        ? Number(merged.halo_width)
        : STYLE_DEFAULTS.halo_width,
      anchor: ['start', 'middle', 'end'].includes(merged.anchor)
        ? merged.anchor
        : STYLE_DEFAULTS.anchor,
    };
  }

  function toCssColor(raw, fallback) {
    if (!raw || raw === 'none') return fallback;
    const value = String(raw).trim();
    const rgb = /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i.exec(value);
    if (rgb) {
      return (
        '#' +
        [1, 2, 3]
          .map((index) =>
            clamp(Math.round(Number(rgb[index])), 0, 255)
              .toString(16)
              .padStart(2, '0')
          )
          .join('')
      );
    }
    if (value.startsWith('#')) return value;
    // 命名颜色等保留原样(SVG 与 matplotlib 都认得).
    return value;
  }

  function weightName(raw) {
    const value = String(raw || 'normal').trim().toLowerCase();
    if (value === '' || value === 'normal' || value === '400') return 'normal';
    if (value === 'bold' || value === '700') return 'bold';
    const numeric = parseInt(value, 10);
    if (Number.isFinite(numeric)) return numeric >= 600 ? 'bold' : 'normal';
    return 'normal';
  }

  function normalizeAngle(degrees) {
    let value = Number(degrees) || 0;
    value %= 360;
    if (value > 180) value -= 360;
    if (value <= -180) value += 360;
    return round3(value);
  }

  function readCoord(raw, fallback) {
    const value = parseFloat(raw);
    return Number.isFinite(value) ? value : fallback;
  }

  function normalizeSpace(text) {
    return String(text || '').replace(/\s+/g, ' ').trim();
  }

  function createSvg(tag, attributes) {
    const element = document.createElementNS(SVG_NS, tag);
    for (const [name, value] of Object.entries(attributes || {})) {
      element.setAttribute(name, value);
    }
    return element;
  }

  function applyMatrix(matrix, x, y) {
    return {
      x: matrix.a * x + matrix.c * y + matrix.e,
      y: matrix.b * x + matrix.d * y + matrix.f,
    };
  }

  function boundsOf(points) {
    const xs = points.map((point) => point.x);
    const ys = points.map((point) => point.y);
    const minX = Math.min(...xs);
    const minY = Math.min(...ys);
    return { x: minX, y: minY, width: Math.max(...xs) - minX, height: Math.max(...ys) - minY };
  }

  function isTypingTarget(target) {
    if (!target || !target.tagName) return false;
    const tag = target.tagName.toLowerCase();
    return (
      tag === 'input' ||
      tag === 'textarea' ||
      tag === 'select' ||
      !!target.isContentEditable
    );
  }

  function isButtonTarget(target) {
    if (!target || !target.tagName) return false;
    const tag = target.tagName.toLowerCase();
    return tag === 'button' || tag === 'a' || tag === 'label';
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function round3(value) {
    const rounded = Math.round(Number(value) * 1000) / 1000;
    return Object.is(rounded, -0) ? 0 : rounded;
  }

  function fmt(value) {
    return String(round3(value));
  }

  function signed(value) {
    const number = round3(value);
    return `${number >= 0 ? '+' : ''}${number.toFixed(2)}`;
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch (error) {
      throw new Error(`${url} 返回的不是 JSON: ${text.slice(0, 200)}`);
    }
    if (!response.ok) {
      throw new Error((data && data.error) || `HTTP ${response.status}`);
    }
    return data;
  }

  // ── 调试/验证接口 ──────────────────────────────────────────

  window.__labelEditor = {
    ready: () => S.editing,
    metrics: () => ({
      readyMs: S.readyAt,
      labelCount: S.labels.size,
      existingCount: existingLabels().length,
      visibleCount: visibleLabels().length,
      addedCount: S.added.length,
      movedCount: Object.keys(S.moved).length,
      scale: S.scale,
      dirty: S.dirty,
      needsRender: S.needsRender,
      viewBox: { ...S.viewBox },
    }),
    state: () => ({
      figure: S.figure,
      svgPath: S.svgPath,
      placementsPath: S.placementsPath,
      error: S.error,
      renderHint: S.renderHint,
      selected: S.selectedId,
      dirty: S.dirty,
      needsRender: S.needsRender,
      saveState: S.saveState,
    }),
    labels: () =>
      visibleLabels().map((label) => ({
        id: label.id,
        text: displayText(label, 80),
        added: !!label.added,
        status: labelStatus(label),
        offset: label.added
          ? addedOffset(S.addedIndex.get(label.id), label)
          : currentOffset(label.id),
        transform: label.node.getAttribute('transform'),
      })),
    labelIds: () => visibleLabels().map((label) => label.id),
    select: (id) => selectLabel(id),
    selectAndCenter: (id) => selectLabel(id, { center: true }),
    deselect,
    fit: fitView,
    zoomTo,
    zoomFactor: (factor) => zoomAt(els.canvas.clientWidth / 2, els.canvas.clientHeight / 2, factor),
    offsetOf: (id) => {
      const label = S.labels.get(id);
      if (!label) return null;
      if (label.added) {
        const record = S.addedIndex.get(id);
        return record ? addedOffset(record, label) : null;
      }
      return currentOffset(id);
    },
    transformOf: (id) => {
      const label = S.labels.get(id);
      return label ? label.node.getAttribute('transform') : null;
    },
    moved: () => JSON.parse(JSON.stringify(S.moved)),
    added: () => JSON.parse(JSON.stringify(S.added)),
    bakedDoc: () => S.baked,
    currentDoc: () => canonicalStateDoc(),
    save: () => save(),
    addAnnotationAt: (x, y, text) => addAnnotation(text, x, y),
    beginPick,
    exitPick,
    isPickMode: () => S.pickMode,
    step: () => stepValue(),
    styleSource: () => (els.styleSource ? els.styleSource.value : ''),
    setStyleSource: (id) => {
      if (els.styleSource) els.styleSource.value = id || '';
    },
    screenOf: (id) => {
      const label = S.labels.get(id);
      if (!label) return null;
      const rect = label.el.getBoundingClientRect();
      return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2, width: rect.width, height: rect.height };
    },
    userToClient,
    setSpace: (held) => {
      S.spaceHeld = !!held;
    },
    isTypingFocused: () => isTypingTarget(document.activeElement),
  };
})();
