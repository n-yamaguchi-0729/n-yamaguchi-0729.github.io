(function renderHomepage() {
    const root = document.getElementById("homepage-root");
    const lang = window.HOMEPAGE_LANG;
    const data = window.HOMEPAGE_DATA;

    if (!root || !lang || !data || !data.pages || !data.pages[lang]) {
        return;
    }

    function isLocalized(value) {
        return value && typeof value === "object" && !Array.isArray(value) && "en" in value && "ja" in value;
    }

    function getLocalized(value) {
        if (typeof value === "string") {
            return value;
        }

        if (isLocalized(value)) {
            return value[lang] || "";
        }

        return "";
    }

    function getHref(value) {
        if (typeof value === "string") {
            return value;
        }

        if (isLocalized(value)) {
            return value[lang] || value.en || value.ja || "";
        }

        return "";
    }

    function renderRichContent(value) {
        if (value == null) {
            return "";
        }

        if (Array.isArray(value)) {
            return value.map(renderRichContent).join("");
        }

        if (typeof value === "string" || isLocalized(value)) {
            return getLocalized(value);
        }

        if (typeof value === "object") {
            if (value.type === "link") {
                const href = getHref(value.href);

                if (!href) {
                    return renderRichContent(value.label);
                }

                return `<a href="${href}" target="_blank" rel="noopener noreferrer">${renderRichContent(value.label)}</a>`;
            }

            if (value.type === "bold") {
                return `<b>${renderRichContent(value.content)}</b>`;
            }

            if (value.type === "italic") {
                return `<i>${renderRichContent(value.content)}</i>`;
            }

            if (value.type === "tag") {
                const className = value.className ? ` class="${value.className}"` : "";
                return `<${value.tagName}${className}>${renderRichContent(value.content)}</${value.tagName}>`;
            }
        }

        return "";
    }

    function renderList(items, options = {}) {
        const tagName = options.ordered ? "ol" : "ul";
        const className = options.className ? ` class="${options.className}"` : "";
        const reversed = options.ordered && options.reversed ? " reversed" : "";

        return `<${tagName}${reversed}${className}>${items.map(renderListItem).join("")}</${tagName}>`;
    }

    function renderListItem(item) {
        const normalizedItem =
            item && typeof item === "object" && !Array.isArray(item) && !isLocalized(item) && !("type" in item)
                ? item
                : { content: item };
        const className = normalizedItem.className ? ` class="${normalizedItem.className}"` : "";
        const content = renderRichContent(normalizedItem.content);
        const children = normalizedItem.children || [];
        const childOptions = normalizedItem.listOptions || {};
        const childrenHtml = children.length ? renderList(children, childOptions) : "";

        return `<li${className}>${content}${childrenHtml}</li>`;
    }

    function renderSectionBody(section) {
        if (section.bodyHtml) {
            return getLocalized(section.bodyHtml);
        }

        if (section.items) {
            return renderList(section.items, {
                ordered: section.ordered,
                reversed: section.reversed,
                className: section.className
            });
        }

        return "";
    }

    const page = data.pages[lang];
    const sectionsHtml = data.sections
        .map((section) => {
            const additionalContent =
                section.id === "intro"
                    ? `
            <div id="additionalContent">
                <p><b>${page.mobileSwitchLabel}</b> <a href="${page.switchHref}">URL</a></p>
            </div>`
                    : "";

            return `
        <section id="${section.id}">
            <h1>${section.title[lang]}</h1>
            ${additionalContent}
            ${renderSectionBody(section)}
        </section>`;
        })
        .join("");

    const sidebarHtml = data.sections
        .map((section) => `<li><a href="#${section.id}">${section.nav[lang]}</a></li>`)
        .join("");

    const headerAuthor = page.header.authorHtml ? `<p class="header_author">${page.header.authorHtml}</p>` : "";

    root.innerHTML = `
    <div class="header">
        <p class="header_words">${page.header.quoteHtml}</p>
        ${headerAuthor}
    </div>

    <div class="container">
        ${sectionsHtml}
    </div>

    <div class="sidebar">
        <nav>
            <ul>
                ${sidebarHtml}
                <li><a href="${page.switchHref}">${page.switchLabel}</a></li>
            </ul>
        </nav>
    </div>`;
})();
