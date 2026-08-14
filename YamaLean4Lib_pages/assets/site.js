(() => {
  "use strict";

  const body = document.body;
  const app = document.getElementById("app");
  const base = body.dataset.base || ".";
  const page = body.dataset.page || "index";
  const catalog = window.YL_CATALOG || { libraries: [] };
  const libraries = new Map(catalog.libraries.map((item) => [item.id, item]));
  const query = new URLSearchParams(location.search);
  const headerCurrent = document.getElementById("header_current");
  const headerSearch = document.getElementById("search_input");
  const autocomplete = document.getElementById("autocomplete_results");

  const h = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
  const q = (value) => encodeURIComponent(value);
  const libraryHref = (id) => `${base}/library.html?library=${q(id)}`;
  const moduleHref = (id, module) => `${base}/module.html?library=${q(id)}&module=${q(module)}`;
  const declarationHref = (id, module, name) => `${moduleHref(id, module)}#decl-${q(name)}`;
  const localImports = (library, module) => {
    const names = new Set(library.modules.map((item) => item.name));
    return module ? module.imports.filter((name) => names.has(name)) : [];
  };

  function setCurrent(value) {
    headerCurrent.textContent = value;
  }

  function loadLibrary(id) {
    window.YL_LIBRARIES = window.YL_LIBRARIES || {};
    if (window.YL_LIBRARIES[id]) return Promise.resolve(window.YL_LIBRARIES[id]);
    if (!libraries.has(id)) return Promise.reject(new Error(`Unknown library: ${id}`));
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = `${base}/data/${q(id)}.js`;
      script.onload = () => resolve(window.YL_LIBRARIES[id]);
      script.onerror = () => reject(new Error(`Could not load ${id}`));
      document.head.appendChild(script);
    });
  }

  function kindCounts(modules) {
    const counts = new Map();
    modules.forEach((module) => module.declarations.forEach((item) => {
      counts.set(item.kind, (counts.get(item.kind) || 0) + 1);
    }));
    return counts;
  }

  function plural(value, singular, pluralName = `${singular}s`) {
    return `${value.toLocaleString()} ${value === 1 ? singular : pluralName}`;
  }

  function declarationSummary(modules) {
    const labels = {
      theorem: "Theorems",
      lemma: "Lemmas",
      def: "Definitions",
      abbrev: "Abbreviations",
      instance: "Instances",
      structure: "Structures",
      class: "Classes",
      inductive: "Inductive types",
      axiom: "Axioms",
      opaque: "Opaque definitions",
      constant: "Constants",
    };
    const counts = kindCounts(modules);
    return [...counts.entries()]
      .filter(([, count]) => count)
      .map(([kind, count]) => `${count.toLocaleString()} ${labels[kind] || kind}`)
      .join(" | ");
  }

  function groupModules(library, prefix, libraryRoot = false) {
    const names = library.modules.map((item) => item.name);
    let effectivePrefix = prefix;
    if (libraryRoot) {
      const allUnderId = names.length > 0 && names.every(
        (name) => name === library.id || name.startsWith(`${library.id}.`),
      );
      effectivePrefix = allUnderId ? library.id : "";
    }
    const groups = new Map();
    library.modules.forEach((module) => {
      if (effectivePrefix && module.name === effectivePrefix) return;
      if (effectivePrefix && !module.name.startsWith(`${effectivePrefix}.`)) return;
      const rest = effectivePrefix
        ? module.name.slice(effectivePrefix.length + 1)
        : module.name;
      const segment = rest.split(".")[0];
      if (!segment) return;
      const fullName = effectivePrefix ? `${effectivePrefix}.${segment}` : segment;
      if (!groups.has(fullName)) groups.set(fullName, []);
      groups.get(fullName).push(module);
    });
    return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right));
  }

  function moduleRows(library, prefix, libraryRoot = false) {
    return groupModules(library, prefix, libraryRoot).map(([fullName, modules]) => {
      const exact = modules.find((item) => item.name === fullName);
      const declarations = modules.reduce((sum, item) => sum + item.declarations.length, 0);
      const label = fullName.split(".").at(-1);
      const description = exact?.documentation
        || modules.find((item) => item.documentation)?.documentation
        || "";
      return `<section class="module-row library-row">
        <h2><a href="${moduleHref(library.id, fullName)}">${h(label)}</a></h2>
        <div class="meta">${plural(modules.length, "file")} | ${plural(declarations, "declaration")}${declarations ? ` | ${h(declarationSummary(modules))}` : ""}</div>
        ${description ? `<div class="sample tex2jax_process">${h(description)}</div>` : ""}
      </section>`;
    }).join("");
  }

  function importDetails(title, names, library) {
    const localNames = new Set(library.modules.map((item) => item.name));
    const content = names.length
      ? `<ul>${names.map((name) => `<li>${localNames.has(name) ? `<a href="${moduleHref(library.id, name)}">${h(name)}</a>` : h(name)}</li>`).join("")}</ul>`
      : '<div class="imports-empty">None</div>';
    return `<details class="imports"><summary>${h(title)}</summary>${content}</details>`;
  }

  function renderIndex() {
    const moduleCount = catalog.libraries.reduce((sum, item) => sum + item.module_count, 0);
    const declarationCount = catalog.libraries.reduce((sum, item) => sum + item.declaration_count, 0);
    setCurrent("");
    document.title = "Yamaguchi Lean 4 Library";
    app.innerHTML = `<section>
      <h1 class="page-title">Yamaguchi Lean 4 Library</h1>
      <p>Lean 4 libraries by Naganori Yamaguchi, developed with AI assistance by a non-specialist. Please use them at your own risk.</p>
      <div class="stats"><span>${plural(catalog.libraries.length, "library", "libraries")}</span><span>${plural(moduleCount, "file")}</span><span>${plural(declarationCount, "declaration")}</span></div>
    </section>
    <div id="library_list">${catalog.libraries.map((library) => `<section class="module-head">
      <div class="module-head-top"><div>
        <div class="eyebrow">Library</div>
        <h2 class="module-title"><a href="${libraryHref(library.id)}">${h(library.display_name)}</a></h2>
        <div class="module-meta">${plural(library.module_count, "file")} | ${plural(library.declaration_count, "declaration")}</div>
        <div class="sample"><p class="library-summary">${h(library.summary)}</p>
          ${library.repository ? `<p class="library-repository"><a href="${h(library.repository)}" target="_blank" rel="noopener">GitHub repository</a></p>` : ""}
        </div>
      </div></div>
    </section>`).join("")}</div>`;
  }

  async function renderLibrary() {
    const id = query.get("library") || "";
    try {
      const library = await loadLibrary(id);
      const root = library.modules.find((item) => item.name === id);
      const groups = groupModules(library, "", true);
      setCurrent(library.id);
      document.title = `${library.id} | Yamaguchi Lean 4 Library`;
      app.innerHTML = `<section class="module-head">
        <div class="module-head-top"><div>
          <div class="eyebrow breadcrumb"><span>${h(library.id)}</span></div>
          <h1 class="module-title">${h(library.id)}</h1>
          <div class="module-meta">${plural(groups.length, "section")} | ${plural(library.modules.length, "file")} | ${plural(library.declaration_count, "declaration")}</div>
          <div class="module-overview tex2jax_process"><p>${h(library.summary)}</p></div>
        </div></div>
        ${root ? importDetails("imports", root.imports, library) : ""}
        ${root ? importDetails("Imported by", library.modules.filter((item) => item.imports.includes(root.name)).map((item) => item.name), library) : ""}
      </section>
      <section><div id="topic_list" class="module-list">${moduleRows(library, "", true) || '<div class="empty">No modules</div>'}</div></section>`;
    } catch (error) {
      app.innerHTML = `<p class="empty">${h(error.message)}</p>`;
    }
  }

  function breadcrumb(library, moduleName) {
    const parts = moduleName.split(".");
    if (parts[0] === library.id) parts.shift();
    const crumbs = [`<a href="${libraryHref(library.id)}">${h(library.id)}</a>`];
    let current = moduleName.startsWith(`${library.id}.`) ? library.id : "";
    parts.forEach((part, index) => {
      current = current ? `${current}.${part}` : part;
      if (index === parts.length - 1) crumbs.push(`<span>${h(part)}</span>`);
      else crumbs.push(`<a href="${moduleHref(library.id, current)}">${h(part)}</a>`);
    });
    return crumbs.join('<span class="sep">/</span>');
  }

  function declarationList(library, module) {
    if (!module || !module.declarations.length) return "";
    return `<section class="decl-toolbar"><h2>Declarations</h2></section>
      <div class="decl-list">${module.declarations.map((item) => {
        const identifier = `decl-${item.name}`;
        const label = item.kind === "def" ? "Definition" : item.kind.charAt(0).toUpperCase() + item.kind.slice(1);
        return `<section class="decl ${h(item.kind)}" id="${h(identifier)}">
          <div class="decl-head"><span class="kind ${h(item.kind)}">${h(label)}</span><a class="decl-name" href="#${q(identifier)}">${h(item.name)}</a></div>
          <div class="pair statement-pair statement-only"><section><pre class="code-box"><code>${h(item.signature || `${item.kind} ${item.name}`)}</code></pre></section></div>
        </section>`;
      }).join("")}</div>`;
  }

  async function renderModule() {
    const id = query.get("library") || "";
    const moduleName = query.get("module") || "";
    try {
      const library = await loadLibrary(id);
      const module = library.modules.find((item) => item.name === moduleName);
      const descendants = library.modules.filter((item) => item.name === moduleName || item.name.startsWith(`${moduleName}.`));
      if (!module && !descendants.length) throw new Error(`Unknown module: ${moduleName}`);
      const children = groupModules(library, moduleName);
      const importedBy = module
        ? library.modules.filter((item) => item.imports.includes(module.name)).map((item) => item.name)
        : [];
      const declarationCount = descendants.reduce((sum, item) => sum + item.declarations.length, 0);
      setCurrent(moduleName);
      document.title = `${moduleName} | Yamaguchi Lean 4 Library`;
      app.innerHTML = `<section class="module-head">
        <div class="module-head-top"><div>
          <div class="eyebrow breadcrumb">${breadcrumb(library, moduleName)}</div>
          <h1 class="module-title">${h(moduleName)}</h1>
          <div class="module-meta">${children.length ? `${plural(children.length, "section")} | ${plural(descendants.length, "file")} | ` : ""}${plural(children.length ? declarationCount : (module?.declarations.length || 0), "declaration")}</div>
          ${module?.documentation ? `<div class="module-overview tex2jax_process"><p>${h(module.documentation)}</p></div>` : ""}
        </div></div>
        ${module ? importDetails("imports", module.imports, library) : ""}
        ${module ? importDetails("Imported by", importedBy, library) : ""}
      </section>
      ${children.length ? `<section><div id="topic_list" class="module-list">${moduleRows(library, moduleName)}</div></section>` : ""}
      ${declarationList(library, module)}`;
    } catch (error) {
      app.innerHTML = `<p class="empty">${h(error.message)}</p>`;
    }
  }

  let searchEntriesPromise;
  function searchEntries() {
    if (searchEntriesPromise) return searchEntriesPromise;
    searchEntriesPromise = Promise.all(catalog.libraries.map((library) => loadLibrary(library.id))).then((loaded) => {
      const entries = [];
      loaded.forEach((library) => {
        entries.push({ type: "library", library: library.id, module: "", kind: "", name: library.display_name, signature: library.summary });
        library.modules.forEach((module) => {
          entries.push({ type: "module", library: library.id, module: module.name, kind: "module", name: module.name, signature: module.documentation });
          module.declarations.forEach((item) => entries.push({ type: "declaration", library: library.id, module: module.name, kind: item.kind, name: item.name, signature: item.signature }));
        });
      });
      return entries;
    });
    return searchEntriesPromise;
  }

  function entryHref(item) {
    if (item.type === "library") return libraryHref(item.library);
    if (item.type === "declaration") return declarationHref(item.library, item.module, item.name);
    return moduleHref(item.library, item.module);
  }

  function searchMatches(entries, pattern, limit) {
    const terms = pattern.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return [];
    return entries.map((item) => {
      const name = item.name.toLocaleLowerCase();
      const shortName = name.split(".").at(-1);
      const module = item.module.toLocaleLowerCase();
      const text = `${name} ${module} ${item.kind} ${item.signature}`.toLocaleLowerCase();
      if (!terms.every((term) => text.includes(term))) return null;
      const needle = terms.join(" ");
      let score = text.includes(needle) ? 30 : 1;
      if (module.includes(needle)) score = 52;
      if (name.includes(needle)) score = 90;
      if (name.endsWith(needle)) score = 108;
      if (shortName.startsWith(needle)) score = 115;
      if (name === needle || shortName === needle) score = 140;
      return { item, score };
    }).filter(Boolean).sort((left, right) => right.score - left.score || left.item.name.localeCompare(right.item.name)).slice(0, limit).map((entry) => entry.item);
  }

  function drawSearchResults(entries, pattern) {
    const results = document.getElementById("search_results");
    const matches = searchMatches(entries, pattern, 200);
    results.innerHTML = pattern.trim()
      ? matches.map((item) => `<article class="search-result">
          <a class="search-result-name" href="${entryHref(item)}">${h(item.name)}</a>
          <div class="result-meta">${h(item.type)}${item.kind ? ` | ${h(item.kind)}` : ""} | ${h(item.library)}${item.module ? ` | ${h(item.module)}` : ""}</div>
          ${item.signature ? `<div class="search-result-doc">${h(item.signature)}</div>` : ""}
        </article>`).join("") || '<div class="empty">No results</div>'
      : '<div class="empty">Enter a search term above.</div>';
  }

  async function renderSearch() {
    const pattern = query.get("pattern") || "";
    setCurrent("Search Results");
    document.title = "Search | Yamaguchi Lean 4 Library";
    headerSearch.value = pattern;
    app.innerHTML = '<section><h1 class="page-title">Search Results</h1></section><section id="search_results" class="search-results tex2jax_process"><div class="tree-loading">Loading</div></section>';
    try {
      const entries = await searchEntries();
      drawSearchResults(entries, pattern);
      headerSearch.addEventListener("input", () => drawSearchResults(entries, headerSearch.value));
    } catch (error) {
      document.getElementById("search_results").innerHTML = `<div class="empty">${h(error.message)}</div>`;
    }
  }

  function treeNode(segment, fullName) {
    return { segment, fullName, module: "", children: new Map() };
  }

  function treeForLibrary(library, activeId, activeModule) {
    const root = treeNode(library.display_name, "");
    const names = library.module_names || [];
    const stripRoot = names.length > 0 && names.every((name) => name === library.id || name.startsWith(`${library.id}.`));
    names.forEach((moduleName) => {
      if (moduleName === library.id) {
        root.module = moduleName;
        return;
      }
      let parts = moduleName.split(".");
      if (stripRoot && parts[0] === library.id) parts = parts.slice(1);
      if (!parts.length) {
        root.module = moduleName;
        return;
      }
      let node = root;
      parts.forEach((part, index) => {
        if (!node.children.has(part)) {
          const prefixParts = stripRoot ? [library.id, ...parts.slice(0, index + 1)] : parts.slice(0, index + 1);
          node.children.set(part, treeNode(part, prefixParts.join(".")));
        }
        node = node.children.get(part);
      });
      node.module = moduleName;
    });
    const libraryActive = activeId === library.id;
    const renderNode = (node) => {
      const children = [...node.children.values()].sort((left, right) => left.segment.localeCompare(right.segment));
      const active = libraryActive && (activeModule === node.module || activeModule.startsWith(`${node.fullName}.`));
      if (!children.length) {
        return `<li class="tree-file${activeModule === node.module ? " active" : ""}"><a href="${moduleHref(library.id, node.module)}">${h(node.segment)}.lean</a></li>`;
      }
      return `<li class="tree-dir${active ? " contains-active" : ""}"><details${active ? " open" : ""}><summary>${h(node.segment)}</summary><ul>
        ${node.module ? `<li class="tree-file${activeModule === node.module ? " active" : ""}"><a href="${moduleHref(library.id, node.module)}">${h(node.segment)}.lean</a></li>` : ""}
        ${children.map(renderNode).join("")}
      </ul></details></li>`;
    };
    return `<li class="tree-dir${libraryActive ? " contains-active" : ""}"><details${libraryActive ? " open" : ""}><summary>${h(library.display_name)}</summary><ul>
      ${root.module ? `<li class="tree-file${activeModule === root.module ? " active" : ""}"><a href="${libraryHref(library.id)}">${h(library.id)}.lean</a></li>` : ""}
      ${[...root.children.values()].sort((left, right) => left.segment.localeCompare(right.segment)).map(renderNode).join("")}
    </ul></details></li>`;
  }

  function renderFileTree() {
    const activeId = query.get("library") || "";
    const activeModule = query.get("module") || (page === "library" ? activeId : "");
    document.querySelector(".file-tree").dataset.active = activeModule;
    document.getElementById("file_tree").innerHTML = `<ul class="tree">${catalog.libraries.map((library) => treeForLibrary(library, activeId, activeModule)).join("")}</ul>`;
    requestAnimationFrame(() => document.querySelector(".tree-file.active")?.scrollIntoView({ block: "center" }));
  }

  function initializeHeaderSearch() {
    let timer;
    headerSearch.addEventListener("input", () => {
      clearTimeout(timer);
      const pattern = headerSearch.value;
      if (!pattern.trim()) {
        autocomplete.innerHTML = "";
        return;
      }
      timer = setTimeout(async () => {
        const entries = await searchEntries();
        autocomplete.innerHTML = searchMatches(entries, pattern, 10).map((item) => `<a href="${entryHref(item)}"><span class="result-name">${h(item.name)}</span><span class="result-meta">${h(item.type)} | ${h(item.library)}</span></a>`).join("");
      }, 90);
    });
    document.querySelector(".search-form").addEventListener("submit", (event) => {
      if (!headerSearch.value.trim()) event.preventDefault();
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".search-form")) autocomplete.innerHTML = "";
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey && !event.target.matches("input,textarea")) {
        event.preventDefault();
        headerSearch.focus();
      }
    });
  }

  renderFileTree();
  initializeHeaderSearch();
  if (page === "index") renderIndex();
  else if (page === "library") renderLibrary();
  else if (page === "module") renderModule();
  else if (page === "search") renderSearch();
})();
