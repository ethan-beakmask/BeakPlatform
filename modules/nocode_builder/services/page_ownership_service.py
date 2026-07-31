"""
NoCode 頁面所屬子系統存活判定服務。

dc_page_layouts 頁面的可達性採「雙路徑 OR」判定：只要有存活的
dc_site_map_nodes 指向該頁面且該節點所屬子系統仍存活，或有存活的
dc_sub_system_pages 掛載該頁面且該掛載所屬子系統仍存活，頁面就視為仍可達。

若頁面沒有任何存活的 site map 節點或子系統掛載，則視為不屬於任何子系統的
純平台 IR 頁面並放行。這是為了避免把平台層獨立頁面誤判成 NoCode 孤兒頁，
因此本服務只根據存活關聯推論，不追溯已軟刪關聯。
"""

from ..models.site_map_node import DcSiteMapNode
from ..models.sub_system import DcSubSystem
from ..models.sub_system_page import DcSubSystemPage


def get_owner_sub_system_codes(page_layout_sc: str) -> set[str]:
    """回傳該頁面所有『存活關聯』指向的子系統 secure_code 集合（去重）。"""
    codes = set()

    site_map_nodes = DcSiteMapNode.query.filter(
        DcSiteMapNode.page_layout_secure_code == page_layout_sc,
        DcSiteMapNode.is_deleted == False,  # noqa: E712
    ).all()
    for node in site_map_nodes:
        sub_system_sc = (node.sub_system_secure_code or '').strip()
        if sub_system_sc:
            codes.add(sub_system_sc)

    sub_system_pages = DcSubSystemPage.query.filter(
        DcSubSystemPage.page_layout_secure_code == page_layout_sc,
        DcSubSystemPage.is_deleted == False,  # noqa: E712
    ).all()
    for page in sub_system_pages:
        sub_system_sc = (page.sub_system_secure_code or '').strip()
        if sub_system_sc:
            codes.add(sub_system_sc)

    return codes


def is_page_reachable(page_layout_sc: str) -> bool:
    """頁面所屬子系統是否還活著；不屬於任何子系統的純平台頁回 True。"""
    owner_codes = get_owner_sub_system_codes(page_layout_sc)
    if not owner_codes:
        return True

    return DcSubSystem.query.filter(
        DcSubSystem.secure_code.in_(owner_codes),
        DcSubSystem.is_deleted == False,  # noqa: E712
    ).count() > 0
