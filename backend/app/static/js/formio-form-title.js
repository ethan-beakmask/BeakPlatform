/**
 * Form.io FormTitle 自訂元件 - 表單名稱元件
 *
 * 功能：
 *   - 顯示表單名稱標題（h3, 置中）
 *   - 設定面板沿用 HTML Element 的設定
 *   - 預設 content: "請設定表單名稱"
 *
 * 註冊方式：Formio.use() 外掛
 */
'use strict';

(function () {
    if (typeof Formio === 'undefined') {
        console.error('[FormTitle] Formio is not loaded');
        return;
    }

    var HtmlElementComponent = Formio.Components.components.htmlelement;
    if (!HtmlElementComponent) {
        console.error('[FormTitle] htmlelement component not found');
        return;
    }

    class FormTitleComponent extends HtmlElementComponent {

        static schema(...extend) {
            return HtmlElementComponent.schema({
                type: 'formTitle',
                tag: 'h3',
                attrs: [
                    { attr: 'style', value: 'text-align:center; margin:0 0 0.5rem 0;' }
                ],
                content: __('請設定表單名稱'),
                key: 'formTitle',
                input: false,
                tableView: false,
            }, ...extend);
        }

        static get builderInfo() {
            return {
                title: __('表單名稱'),
                group: 'custom',
                icon: 'fas fa-heading',
                weight: 20,
                schema: FormTitleComponent.schema(),
            };
        }

        get defaultSchema() {
            return FormTitleComponent.schema();
        }
    }

    Formio.use({
        components: {
            formTitle: FormTitleComponent,
        },
    });
})();
