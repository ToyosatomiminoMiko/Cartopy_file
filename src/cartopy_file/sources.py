# -*- coding: utf-8 -*-
# (copyright) Kawaii Femboy Technology Co., Ltd.
"""Registry of external data sources: URL templates, versions, licenses, credits.

是什么: 全项目外部数据源的唯一登记处. 每个数据源只在这里写一次 URL 模板,版本口径,
许可与进图署名; 各子项目的 ``datasets.py`` 只引用 ``Source.id``, 不再各自硬编码网址.
完整说明(为什么集中,版本怎么钉,署名进图的口径)见 ``docs/reference/datasets.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "SOURCES",
    "Source",
    "erddap_url",
    "gadm_url",
    "hydrobasins_url",
    "ne_url",
    "overpass_endpoints",
    "source",
]

# 下载时的 User-Agent: 个别站点(S3/ERDDAP)会对默认的 "Python-urllib" 限速或拒绝.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

# Overpass 公共实例: 依次尝试, 前一个 502/超时就换下一个.
# 这是实时查询接口, 不提供文件版本, 所以只能把拿到的结果当快照用(见 注意事项).
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)


@dataclass(frozen=True)
class Source:
    """一个外部数据源; 字段就是「要写进文档和产物」的全部事实.

    version: 版本口径. 有版本号的用版本号(如 GADM 的 4.1), 版本写在文件名/URL 里的
        照抄(如 ``v1c``), 完全没有版本概念的留空字符串(如 Overpass).
    url: 下载地址模板; 需要参数的用 ``str.format`` 占位, 由下面的 ``*_url`` 函数填.
    homepage: 人类可读的发布页. 产物里的「数据来源」写这个 URL, 因为它长期有效,
        而下载地址(S3 路径,ERDDAP 查询串)会随参数变化, 不适合给人看.
    credit: 进图的署名短句, 含许可要求必须出现的文字(如 ODbL 的
        ``© OpenStreetMap contributors``); 多个数据集共用同一 source 时只出现一次.
    """

    id: str
    title: str
    version: str
    url: str
    homepage: str
    license: str
    credit: str

    @property
    def citation(self) -> str:
        """产物「数据来源」里的一条: 署名 + 发布页 URL."""
        return f"{self.credit} {self.homepage}"


SOURCES: dict[str, Source] = {
    source.id: source
    for source in (
        Source(
            id="natural-earth",
            title="Natural Earth",
            # S3 路径不带版本: Natural Earth 换版会原地覆盖同名文件. 版本只能靠
            # 缓存目录里的 *.VERSION.txt 钉住(见 docs/reference/datasets.md).
            version="5.1.1",
            url="https://naturalearth.s3.amazonaws.com/{resolution}_{category}/{name}.zip",
            homepage="https://www.naturalearthdata.com",
            license="public domain",
            credit="Natural Earth 5.1.1",
        ),
        Source(
            id="etopo-2022",
            title="NOAA ETOPO 2022",
            version="v1 (15 arc-second)",
            # 查询串由 erddap_url() 拼: 经度 0~360,stride 是索引步长.
            url="https://oceanwatch.pifsc.noaa.gov/erddap/griddap/ETOPO_2022_v1_15s.nc",
            homepage="https://www.ncei.noaa.gov/products/etopo-global-relief-model",
            license="public domain (US Government work)",
            credit="NOAA ETOPO 2022 (15″)",
        ),
        Source(
            id="gadm-4.1",
            title="GADM",
            version="4.1",
            url="https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_{iso}_1.json",
            homepage="https://gadm.org",
            license="free for academic and non-commercial use",
            credit="GADM 4.1",
        ),
        Source(
            id="hydrobasins",
            title="HydroBASINS (HydroSHEDS)",
            version="v1c",
            # 下载路径里的区域层级(此处欧洲 5 级)由子项目覆盖.
            url="https://data.hydrosheds.org/file/HydroBASINS/standard/{archive}",
            homepage="https://www.hydrosheds.org/products/hydrobasins",
            license="free, attribution required",
            credit="HydroBASINS (HydroSHEDS) v1c",
        ),
        Source(
            id="ocha-hno-2021",
            title="OCHA 2021 HNO GCA/NGCA",
            version="2021",
            url="https://data.humdata.org/dataset/0a24205d-084c-4ef9-9d53-9349bacbde1e/",
            homepage="https://data.humdata.org/dataset/0a24205d-084c-4ef9-9d53-9349bacbde1e/",
            license="per HDX dataset page",
            credit="OCHA 2021 HNO",
        ),
        Source(
            id="openstreetmap",
            title="OpenStreetMap",
            version="",
            url=OVERPASS_ENDPOINTS[0],
            homepage="https://www.openstreetmap.org/copyright",
            license="ODbL 1.0",
            # ODbL 要求署名文字, 不能省略.
            credit="© OpenStreetMap contributors (ODbL)",
        ),
    )
}


def source(source_id: str) -> Source:
    """按 id 取数据源; id 写错时立刻报错, 并列出已登记的 id."""
    try:
        return SOURCES[source_id]
    except KeyError:
        raise KeyError(
            f"未登记的数据源 {source_id!r}; 已登记: {sorted(SOURCES)}"
        ) from None


def ne_url(resolution: str, category: str, name: str) -> str:
    """Natural Earth 单个图层的下载地址(与 cartopy 的 NEShpDownloader 同一口径)."""
    return source("natural-earth").url.format(
        resolution=resolution, category=category, name=name
    )


def erddap_url(
    source_id: str,
    *,
    stride: int,
    lon_range: tuple[float, float],
    lat_range: tuple[float, float],
) -> str:
    """NOAA ERDDAP 动态子集地址.

    查询里的数字是坐标值(用括号括起), stride 是索引步长: 步长 2 即 30 弧秒.
    ERDDAP 的经度是 0~360°, 跨 180° 的区域调用方要先把负经度 +360 再传进来.
    """
    base = source(source_id).url
    min_lon, max_lon = lon_range
    min_lat, max_lat = lat_range
    query = (
        f"z%5B({min_lat}):{stride}:({max_lat})%5D"
        f"%5B({min_lon}):{stride}:({max_lon})%5D"
    )
    return f"{base}?{query}"


def gadm_url(iso: str) -> str:
    """GADM 4.1 一级行政区 JSON 地址(iso 用三字母代码, 如 RUS)."""
    return source("gadm-4.1").url.format(iso=iso)


def hydrobasins_url(archive: str) -> str:
    """HydroBASINS 压缩包地址(archive 形如 hybas_eu_lev05_v1c.zip)."""
    return source("hydrobasins").url.format(archive=archive)


def overpass_endpoints() -> tuple[str, ...]:
    """Overpass 查询接口; 按顺序轮换, 全部失败才算失败."""
    return OVERPASS_ENDPOINTS
