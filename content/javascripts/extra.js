/* ==========================================================================
   Jiangsu Zikao AIO - Interactive UI/UX Enhancements
   ========================================================================== */

if (document.readyState === "complete" || document.readyState === "interactive") {
  initUIEnhancements();
} else {
  document.addEventListener("DOMContentLoaded", () => {
    initUIEnhancements();
  });
}

// Support MkDocs Material instant loading
if (typeof document$ !== "undefined") {
  document$.subscribe(() => {
    initUIEnhancements();
  });
} else if (typeof app !== "undefined" && app.document$) {
  app.document$.subscribe(() => {
    initUIEnhancements();
  });
}

function initUIEnhancements() {
  enhanceCourseCrossLinks();
  enhanceExternalLinks();
  enhanceTables();
}

/**
 * Transforms plain markdown cross-link bars (separated by "｜")
 * into a modern segmented ribbon navigation.
 */
function enhanceCourseCrossLinks() {
  const currentPath = window.location.pathname;
  const paragraphs = document.querySelectorAll(".md-typeset p");

  paragraphs.forEach(p => {
    // Process paragraphs that contain pipe separator and at least 3 markdown links
    if ((p.textContent.includes("｜") || p.textContent.includes("|")) && p.querySelectorAll("a").length >= 3) {
      if (p.classList.contains("zk-cross-link-ribbon")) return;

      p.classList.add("zk-cross-link-ribbon");
      const links = p.querySelectorAll("a");

      links.forEach(a => {
        const href = a.getAttribute("href");
        if (!href) return;

        // Highlight active page
        if (
          href === "./" ||
          href === "index.md" ||
          href === "index.html" ||
          currentPath.endsWith(href) ||
          currentPath.endsWith(href.replace(".md", "/")) ||
          currentPath.endsWith(href.replace(".md", ".html"))
        ) {
          // Check if it matches current page
          const linkFilename = href.split("/").pop().replace(".html", "").replace(".md", "");
          const currentFilename = currentPath.split("/").filter(Boolean).pop() || "index";

          if (linkFilename === currentFilename || (linkFilename === "index" && (currentPath.endsWith("/") || currentFilename.length === 5))) {
            a.classList.add("is-active");
          }
        }
      });

      // Remove plain text pipe characters between links for cleaner UI
      Array.from(p.childNodes).forEach(node => {
        if (node.nodeType === Node.TEXT_NODE && (node.textContent.includes("｜") || node.textContent.includes("|"))) {
          node.textContent = " ";
        }
      });
    }
  });
}

/**
 * Ensures external links open in a new tab with security attributes.
 */
function enhanceExternalLinks() {
  const links = document.querySelectorAll('.md-typeset a[href^="http://"], .md-typeset a[href^="https://"]');
  const currentHost = window.location.hostname;

  links.forEach(link => {
    try {
      const url = new URL(link.href);
      if (url.hostname !== currentHost && url.hostname !== "localhost" && url.hostname !== "127.0.0.1") {
        link.setAttribute("target", "_blank");
        link.setAttribute("rel", "noopener noreferrer");
      }
    } catch (e) {
      // Ignore invalid URLs
    }
  });
}

/**
 * Wraps tables without wrapper in a responsive scroll container.
 */
function enhanceTables() {
  const tables = document.querySelectorAll(".md-typeset table:not([class])");
  tables.forEach(table => {
    if (table.parentElement && !table.parentElement.classList.contains("md-typeset__table")) {
      const wrapper = document.createElement("div");
      wrapper.className = "md-typeset__table";
      table.parentNode.insertBefore(wrapper, table);
      wrapper.appendChild(table);
    }
  });
}
