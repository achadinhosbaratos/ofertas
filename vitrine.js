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
    chips.forEach(button => button.setAttribute("aria-pressed", String(button.dataset.category === category)));
    const favoriteChip = document.getElementById("favorites-filter");
    favoriteChip.setAttribute("aria-pressed", String(onlyFavorites));
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
    // Categorias e Meus favoritos são modos de navegação alternativos.
    onlyFavorites = false;
    apply();
  }));
  document.getElementById("favorites-filter").addEventListener("click", () => {
    const activating = !onlyFavorites;
    onlyFavorites = activating;
    // Mostrar TODOS os favoritos independentemente da categoria, busca ou
    // limites anteriores. Ao sair, voltar à vitrine geral.
    category = "Todas";
    if (activating) {
      search.value = "";
      price.value = "";
      discount.value = "";
    }
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

  async function share(title, url) {
    try {
      if (navigator.share) {
        await navigator.share({title, url});
        return;
      }
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(url);
        notice("Link copiado! Agora é só compartilhar.");
        return;
      }
    } catch (error) {
      if (error && error.name === "AbortError") return;
    }
    const message = encodeURIComponent(title + " " + url);
    window.open("https://wa.me/?text=" + message, "_blank", "noopener,noreferrer");
  }
  document.querySelectorAll(".share-item").forEach(button => {
    button.addEventListener("click", () => {
      const card = button.closest(".card");
      const url = new URL(window.location.href);
      url.search = "";
      url.hash = card.id;
      share(card.querySelector("h3").textContent + " — Achadinhos Baratos", url.href);
    });
  });
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