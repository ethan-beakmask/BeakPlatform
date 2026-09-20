---
title: 表單範本
audience: ORG_ADMIN
order: 20
nav_menu: form_workflow.templates
---

# 表單範本

!!! note "內容撰寫中"
    這個章節的操作說明尚未撰寫。

## 系統申請單專用元件

設計器左側的「系統申請單專用」群組（企業管理員以上才看得到，預設收合）有三個元件。它們是兩項平台功能的零件，**只有搭配指定的流程節點才有作用，放進一般業務表單不會有任何效果**。

| 元件 | 用途 | 搭配節點 | 說明 |
|------|------|----------|------|
| API表單選擇 | 讓申請人勾選「這把 API Key 可以代填哪些表單」，只列出 Key 歸屬人自己填得到的表單 | ApiKeyIssue | [API Key 管理](../05_security_ops/api_keys.md) |
| 代理限定表單選擇 | 讓申請人限定「代理人只能代簽哪幾種表單」 | OpProxyGrant | [設定代理人](../07_daily_work/my_delegation.md) |
| 可委任角色選擇 | 讓申請人勾選「要把自己的哪些角色暫時交給代理人」，只列出本人正式持有的角色 | OpProxyGrant | [設定代理人](../07_daily_work/my_delegation.md) |

出廠的「API Key 申請單」與「代理指定申請單」已經接好，一般情況不需要自己拖這三個元件。
