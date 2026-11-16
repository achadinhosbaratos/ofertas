(() => {
  "use strict";
  const cardsNode = document.getElementById("cards");
  const cards = Array.from(cardsNode.querySelectorAll(".card"));
  const search = document.getElementById("busca");
  const price = document.getElementById("preco-max");
  const discount = document.getElementById("desconto-min");
  const sort = document.getElementById("ordenar");
  const count = document.getElementById("results-count");
  const empty = document.getElementById("empty-state");
  const chips = Array.from(document.querySelectorAll(".category-chip"));
  const clearButtons = Array.from(document.querySelectorAll("[data-clear]"));
  const status = document.getElementById("feedback");
  let category = "Todas";
  let onlyFavorites = false;

  const normalize = value => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const getFavorites = () => {
    try {
      const saved = JSON.parse(localStorage.getItem("achadinhos-favoritos-v2") || "[]");
      return new Set(Array.isArray(saved) ? saved.filter(x => typeof x === "string") : []);
    } catch (_) { return new Set(); }
  };
  let favorites = getFavorites();
  // Migra favoritos marcados na versão anterior sem descartar IDs antigos.
  let migrated = false;
  cards.forEach(card => {
    if (card.dataset.legacyId && favorites.has(card.dataset.legacyId) && !favorites.has(card.id)) {
      favorites.add(card.id);
      migrated = true;
    }
  });
  if (migrated) {
    try { localStorage.setItem("achadinhos-favoritos-v2", JSON.stringify([...favorites])); }
    catch (_) { /* A migração continua válida na aba atual. */ }
  }

  function notice(message) {
    status.textContent = message;
    status.hidden = false;
    clearTimeout(notice.timer);
    notice.timer = setTimeout(() => { status.hidden = true; }, 2700);
  }

  function apply() {
    const q = normalize(search.value.trim());
    const max = Number(price.value || Infinity);
    const minDiscount = Number(discount.value || 0);
    const visible = cards.filter(card => {
      const priceValue = Number(card.dataset.price || 0);
      const discountValue = Number(card.dataset.discount || 0);
      const match = (!q || normalize(card.dataset.search).includes(q))
        && (category === "Todas" || card.dataset.category === category)
        && priceValue <= max
        && discountValue >= minDiscount
        && (!onlyFavorites || favorites.has(card.id));
      card.hidden = !match;
      return match;
    });
    const mode = sort.value;
    const sorter = {
      recentes: (a,b) => b.dataset.date.localeCompare(a.dataset.date),
      barato: (a,b) => Number(a.dataset.price) - Number(b.dataset.price),
      caro: (a,b) => Number(b.dataset.price) - Number(a.dataset.price),
      desconto: (a,b) => Number(b.dataset.discount) - Number(a.dataset.discount),
    }[mode];
    if (sorter) {
      const fragment = document.createDocumentFragment();
      visible.sort(sorter).forEach(card => fragment.append(card));
      cards.filter(card => card.hidden).forEach(card => fragment.append(card));
      cardsNode.append(fragment);
    }
    count.textContent = visible.length + (visible.length === 1 ? " oferta encontrada" : " ofertas encontradas");
    empty.hidden = visible.length > 0;
    if (visible.length === 0) {
      const emptyTitle = empty.querySelector("h3");
      const emptyDescription = empty.querySelector("p");
      if (onlyFavorites && favorites.size === 0) {
        emptyTitle.textContent = "Você ainda não salvou favoritos.";
        emptyDescription.textContent = "Toque no coração dos produtos para guardá-los aqui.";
      } else {
        emptyTitle.textContent = "Ops! Nenhum achadinho por aqui.";
        emptyDescription.textContent = "Tente remover algum filtro ou buscar outro produto.";
      }
    }
    chips.filter(button => button.dataset.category).forEach(button => button.setAttribute("aria-pressed", String(button.dataset.category === category)));
    const favoriteChip = document.getElementById("favorites-filter");
    favoriteChip.setAttribute("aria-pressed", String(onlyFavorites));
    favoriteChip.textContent = onlyFavorites ? "♥ Só favoritos" : "♡ Meus favoritos";
    const summary = document.getElementById("active-filters");
    if (summary) {
      summary.replaceChildren();
      const active = [];
      if (category !== "Todas") active.push({ label: "Categoria: " + category, clear: () => { category = "Todas"; } });
      if (onlyFavorites) active.push({ label: "♥ Favoritos", clear: () => { onlyFavorites = false; } });
      if (q) active.push({ label: "Busca: " + search.value.trim(), clear: () => { search.value = ""; } });
      if (price.value) active.push({ label: "Até R$ " + price.value, clear: () => { price.value = ""; } });
      if (minDiscount) active.push({ label: "Desconto: " + minDiscount + "%+", clear: () => { discount.value = ""; } });
      if (sort.value !== "recentes") active.push({ label: "Ordem: " + sort.selectedOptions[0].textContent, clear: () => { sort.value = "recentes"; } });
      if (!active.length) {
        summary.textContent = "Use os filtros acima para encontrar seu achadinho.";
      } else {
        active.forEach(item => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "filter-tag";
          button.textContent = item.label + " ×";
          button.setAttribute("aria-label", "Remover filtro " + item.label);
          button.addEventListener("click", () => { item.clear(); apply(); });
          summary.append(button);
        });
      }
    }
    const favoriteHint = document.getElementById("all-favorites");
    if (favoriteHint) favoriteHint.hidden = !(visible.length === 0 && onlyFavorites && category !== "Todas" && favorites.size > 0);
    if (visible.length === 0 && onlyFavorites && favorites.size > 0) {
      const emptyTitle = empty.querySelector("h3");
      const emptyDescription = empty.querySelector("p");
      emptyTitle.textContent = "Nenhum favorito corresponde aos filtros.";
      emptyDescription.textContent = category !== "Todas"
        ? "Você não tem favoritos de " + category + " com esses filtros. Veja todos os favoritos ou ajuste sua busca."
        : "Tente ajustar o preço, desconto ou busca para encontrar seus produtos salvos.";
    }
  }

  function reset() {
    search.value = "";
    price.value = "";
    discount.value = "";
    sort.value = "recentes";
    category = "Todas";
    onlyFavorites = false;
    apply();
    search.focus();
  }

  [search,price,discount,sort].forEach(el => el.addEventListener(el === search ? "input" : "change", apply));
  chips.filter(button => button.dataset.category).forEach(button => button.addEventListener("click", () => {
    category = button.dataset.category;
    // A categoria não modifica o filtro de favoritos (e vice-versa).
    apply();
  }));
  document.getElementById("favorites-filter").addEventListener("click", () => {
    onlyFavorites = !onlyFavorites;
    // Conserva categoria, busca, preço e desconto selecionados.
    apply();
  });
  const allFavorites = document.getElementById("all-favorites");
  if (allFavorites) allFavorites.addEventListener("click", () => {
    category = "Todas";
    search.value = "";
    price.value = "";
    discount.value = "";
    onlyFavorites = true;
    apply();
  });
  clearButtons.forEach(button => button.addEventListener("click", reset));

  document.querySelectorAll(".favorite").forEach(button => {
    const id = button.closest(".card").id;
    button.setAttribute("aria-pressed", String(favorites.has(id)));
    button.textContent = favorites.has(id) ? "♥" : "♡";
    button.addEventListener("click", () => {
      if (favorites.has(id)) favorites.delete(id);
      else favorites.add(id);
      try { localStorage.setItem("achadinhos-favoritos-v2", JSON.stringify([...favorites])); }
      catch (_) { notice("Não foi possível guardar os favoritos neste navegador."); }
      button.setAttribute("aria-pressed", String(favorites.has(id)));
      button.textContent = favorites.has(id) ? "♥" : "♡";
      button.setAttribute("aria-label", favorites.has(id) ? "Remover dos favoritos" : "Adicionar aos favoritos");
      apply();
    });
  });

  async function copyLink(url) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(url);
        notice("Link da Shopee copiado!");
        return;
      }
    } catch (_) { /* oferece campo de cópia abaixo */ }
    // Fallback compatível com navegadores antigos, sem abrir links externos.
    const box = document.createElement("textarea");
    box.value = url;
    box.style.position = "fixed";
    box.style.opacity = "0";
    document.body.append(box);
    box.select();
    let copied = false;
    try { copied = document.execCommand("copy"); } catch (_) {}
    box.remove();
    if (copied) notice("Link da Shopee copiado!");
    else window.prompt("Copie o link do produto:", url);
  }

  async function share(title, url) {
    try {
      if (navigator.share) {
        await navigator.share({ title, url });
        return;
      }
      await copyLink(url);
    } catch (error) {
      if (error && error.name === "AbortError") return;
      await copyLink(url);
    }
  }

  function closeShares(exception) {
    document.querySelectorAll(".share-item").forEach(button => {
      if (button === exception) return;
      button.setAttribute("aria-expanded", "false");
      button.closest(".card").querySelector(".share-menu").hidden = true;
    });
  }
  document.querySelectorAll(".share-item").forEach(button => {
    const card = button.closest(".card");
    const menu = card.querySelector(".share-menu");
    const link = card.querySelector(".shop-link").href;
    const productName = card.querySelector("h3").textContent;
    button.addEventListener("click", event => {
      event.stopPropagation();
      const wasOpen = !menu.hidden;
      closeShares(button);
      menu.hidden = wasOpen;
      button.setAttribute("aria-expanded", String(!wasOpen));
    });
    menu.querySelector(".share-whatsapp").addEventListener("click", () => {
      const message = productName + " — " + card.querySelector(".price").textContent +
        " (preço sujeito a alteração). Veja na Shopee: " + link;
      window.open("https://wa.me/?text=" + encodeURIComponent(message), "_blank", "noopener,noreferrer");
      closeShares();
    });
    menu.querySelector(".share-copy").addEventListener("click", () => {
      copyLink(link);
      closeShares();
    });
  });
  document.addEventListener("click", event => {
    if (!event.target.closest(".share-menu") && !event.target.closest(".share-item")) closeShares();
  });
  document.addEventListener("keydown", event => { if (event.key === "Escape") closeShares(); });
  document.querySelectorAll("[data-share-site]").forEach(button => {
    button.addEventListener("click", () => share("Achadinhos Baratos — encontre ofertas", location.href));
  });

  // A âncora compartilhada pode apontar para um item filtrado. Revela e destaca.
  if (location.hash && location.hash.startsWith("#oferta-")) {
    const anchor = document.getElementById(location.hash.slice(1));
    if (anchor) {
      setTimeout(() => anchor.scrollIntoView({block: "center", behavior: "smooth"}), 120);
    }
  }
  apply();
})();