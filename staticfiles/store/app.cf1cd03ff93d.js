const menuButton = document.querySelector(".menu-toggle");
const subnav = document.querySelector(".subnav");

document.querySelectorAll(".search").forEach((form) => {
  const input = form.querySelector('input[name="q"]');
  const datalist = form.querySelector("datalist");
  const suggestionList = form.querySelector(".search-suggestions");
  if (!input || !datalist || !suggestionList) return;

  const suggestions = Array.from(datalist.options, (option) => option.value);
  const hideSuggestions = () => {
    suggestionList.hidden = true;
    input.setAttribute("aria-expanded", "false");
  };
  const showSuggestions = () => {
    const query = input.value.trim().toLocaleLowerCase();
    const matches = suggestions
      .filter((suggestion) => !query || suggestion.toLocaleLowerCase().includes(query))
      .slice(0, 6);
    suggestionList.replaceChildren();
    matches.forEach((suggestion) => {
      const option = document.createElement("button");
      option.className = "search-suggestion";
      option.type = "button";
      option.setAttribute("role", "option");
      option.textContent = suggestion;
      option.addEventListener("click", () => {
        input.value = suggestion;
        hideSuggestions();
        form.requestSubmit();
      });
      suggestionList.append(option);
    });
    suggestionList.hidden = matches.length === 0;
    input.setAttribute("aria-expanded", String(matches.length > 0));
  };

  input.addEventListener("focus", showSuggestions);
  input.addEventListener("input", showSuggestions);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideSuggestions();
  });
  document.addEventListener("click", (event) => {
    if (!form.contains(event.target)) hideSuggestions();
  });
});

menuButton?.addEventListener("click", () => {
  const isOpen = menuButton.getAttribute("aria-expanded") === "true";
  menuButton.setAttribute("aria-expanded", String(!isOpen));
  subnav?.classList.toggle("is-open", !isOpen);
});

document.querySelectorAll(".toast button").forEach((button) => {
  button.addEventListener("click", () => button.closest(".toast")?.remove());
});

document.querySelector("[data-show-more-colors]")?.addEventListener("click", (event) => {
  const button = event.currentTarget;
  const group = button.closest(".catalog-filter-group--colors");
  const expanded = button.getAttribute("aria-expanded") === "true";
  button.setAttribute("aria-expanded", String(!expanded));
  button.textContent = expanded ? "Yana 10" : "Kamroq";
  group?.classList.toggle("is-expanded", !expanded);
});

document.querySelector("[data-clear-filters]")?.addEventListener("click", (event) => {
  const form = event.currentTarget.closest("form");
  if (!form) return;
  form.querySelectorAll('input[name="brand"], input[name="color"], input[name="season"], input[name="min_price"], input[name="max_price"]').forEach((input) => {
    if (input.type === "checkbox") input.checked = false;
    else input.value = "";
  });
  form.querySelectorAll('select[name="sort"]').forEach((select) => {
    select.value = "";
  });
  form.requestSubmit();
});

document.querySelectorAll("[data-price-range]").forEach((slider) => {
  const form = slider.closest("form");
  const minimumInput = form?.querySelector('input[name="min_price"]');
  const maximumInput = form?.querySelector('input[name="max_price"]');
  const minimumRange = slider.querySelector("[data-price-range-min]");
  const maximumRange = slider.querySelector("[data-price-range-max]");
  if (!minimumInput || !maximumInput || !minimumRange || !maximumRange) return;

  const minimum = Number(minimumRange.min);
  const maximum = Number(minimumRange.max);
  const clamp = (value) => Math.min(maximum, Math.max(minimum, Number(value)));
  const updateTrack = () => {
    const span = maximum - minimum;
    const start = span ? ((Number(minimumRange.value) - minimum) / span) * 100 : 0;
    const end = span ? ((Number(maximumRange.value) - minimum) / span) * 100 : 100;
    slider.style.setProperty("--range-start", `${start}%`);
    slider.style.setProperty("--range-end", `${end}%`);
  };
  const updateFromRanges = () => {
    if (Number(minimumRange.value) > Number(maximumRange.value)) {
      if (document.activeElement === minimumRange) maximumRange.value = minimumRange.value;
      else minimumRange.value = maximumRange.value;
    }
    minimumInput.value = minimumRange.value === String(minimum) ? "" : minimumRange.value;
    maximumInput.value = maximumRange.value === String(maximum) ? "" : maximumRange.value;
    updateTrack();
  };
  const updateFromInputs = () => {
    const minimumValue = minimumInput.value === "" ? minimum : clamp(minimumInput.value);
    const maximumValue = maximumInput.value === "" ? maximum : clamp(maximumInput.value);
    minimumRange.value = String(Math.min(minimumValue, maximumValue));
    maximumRange.value = String(Math.max(minimumValue, maximumValue));
    updateTrack();
  };

  minimumRange.addEventListener("input", updateFromRanges);
  maximumRange.addEventListener("input", updateFromRanges);
  minimumInput.addEventListener("input", updateFromInputs);
  maximumInput.addEventListener("input", updateFromInputs);
  updateFromInputs();
});

document.querySelectorAll(".product-season-field").forEach((field) => {
  const form = field.closest("form");
  const category = form?.querySelector('[name="category"]');
  const season = field.querySelector('[name="season"]');
  if (!category || !season) return;

  const updateSeasonField = () => {
    const isClothing = category.value === "Kiyim";
    field.hidden = !isClothing;
    if (!isClothing) season.value = "";
  };

  category.addEventListener("change", updateSeasonField);
  updateSeasonField();
});

const statusUrl = document.body.dataset.topupStatusUrl;
const notificationHost = document.querySelector("[data-app-notifications]");
const soundToggle = document.querySelector("[data-notification-sound]");
const storageKey = `uzum-topup-status-${document.body.dataset.userId}`;
let previousStatuses = {};
let hasStatusSnapshot = false;
let audioContext;
let soundEnabled = false;

if (statusUrl && notificationHost) {
  try {
    previousStatuses = JSON.parse(localStorage.getItem(storageKey) || "{}");
    hasStatusSnapshot = Object.keys(previousStatuses).length > 0;
    soundEnabled = localStorage.getItem("uzum-notification-sound") === "on";
  } catch {
    previousStatuses = {};
  }
  document.querySelectorAll("[data-topup-id]").forEach((row) => {
    const key = String(row.dataset.topupId);
    const status = row.querySelector(".topup-status");
    if (previousStatuses[key] === undefined && status) {
      previousStatuses[key] = status.className.match(/topup-status--(\w+)/)?.[1];
    }
  });
  document.querySelectorAll("[data-card-request-id]").forEach((row) => {
    const key = `card-${row.dataset.cardRequestId}`;
    const status = row.querySelector(".topup-status");
    if (previousStatuses[key] === undefined && status) {
      previousStatuses[key] = status.className.match(/topup-status--(\w+)/)?.[1];
    }
  });
  document.querySelectorAll("[data-order-status]").forEach((status) => {
    const key = `order-${status.dataset.orderStatus}`;
    const orderStatus = status.className.match(/profile-status--(\w+)/)?.[1];
    if (previousStatuses[key] === undefined && orderStatus) previousStatuses[key] = orderStatus;
  });
  hasStatusSnapshot = Object.keys(previousStatuses).length > 0;

  const updateSoundToggle = () => {
    soundToggle?.setAttribute("aria-pressed", String(soundEnabled));
    soundToggle?.setAttribute("title", soundEnabled ? "Bildirishnoma ovozini o‘chirish" : "Bildirishnoma ovozini yoqish");
    soundToggle?.setAttribute("aria-label", soundEnabled ? "Bildirishnoma ovozini o‘chirish" : "Bildirishnoma ovozini yoqish");
    soundToggle?.classList.toggle("is-enabled", soundEnabled);
  };

  const playNotificationSound = async () => {
    if (!soundEnabled) return;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    audioContext ||= new AudioContextClass();
    if (audioContext.state === "suspended") await audioContext.resume();
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();
    oscillator.connect(gain);
    gain.connect(audioContext.destination);
    oscillator.frequency.value = 880;
    gain.gain.setValueAtTime(0.001, audioContext.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.16, audioContext.currentTime + 0.025);
    gain.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.42);
    oscillator.start();
    oscillator.stop(audioContext.currentTime + 0.43);
  };

  soundToggle?.addEventListener("click", async () => {
    soundEnabled = !soundEnabled;
    try {
      localStorage.setItem("uzum-notification-sound", soundEnabled ? "on" : "off");
    } catch {}
    updateSoundToggle();
    if (soundEnabled) await playNotificationSound();
  });
  updateSoundToggle();

  const showNotification = (message) => {
    const toast = document.createElement("div");
    toast.className = "toast topup-notification";
    toast.setAttribute("role", "status");
    toast.textContent = message;
    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.setAttribute("aria-label", "Xabarni yopish");
    closeButton.textContent = "×";
    closeButton.addEventListener("click", () => toast.remove());
    toast.append(closeButton);
    notificationHost.append(toast);
    window.setTimeout(() => toast.remove(), 3000);
    playNotificationSound().catch(() => {});
  };

  const pollTopupStatus = async () => {
    try {
      const response = await fetch(statusUrl, { headers: { "X-Requested-With": "XMLHttpRequest" } });
      if (!response.ok) return;
      const data = await response.json();
      const nextStatuses = {};
      for (const topup of data.requests) {
        const key = String(topup.id);
        nextStatuses[key] = topup.status;
        const row = document.querySelector(`[data-topup-id="${key}"]`);
        const status = row?.querySelector(".topup-status");
        if (status) {
          status.className = `topup-status topup-status--${topup.status}`;
          status.textContent = topup.label;
        }
        if (hasStatusSnapshot && previousStatuses[key] === "pending" && topup.status !== "pending") {
          const message = topup.status === "approved"
            ? `Balansingiz ${Number(topup.amount).toLocaleString("uz-UZ")} so‘mga to‘ldirildi. Admin tasdiqladi.`
            : `Balans to‘ldirish so‘rovingiz rad etildi.`;
          showNotification(message);
        }
      }
      for (const cardRequest of data.card_requests || []) {
        const key = `card-${cardRequest.id}`;
        nextStatuses[key] = cardRequest.status;
        const row = document.querySelector(`[data-card-request-id="${cardRequest.id}"]`);
        const status = row?.querySelector(".topup-status");
        if (status) {
          status.className = `topup-status topup-status--${cardRequest.status}`;
          status.textContent = cardRequest.label;
        }
        if (hasStatusSnapshot && previousStatuses[key] === "pending" && cardRequest.status !== "pending") {
          const action = cardRequest.action === "add" ? "Karta qo‘shish" : "Kartani o‘chirish";
          const outcome = cardRequest.status === "approved" ? "tasdiqlandi" : "rad etildi";
          showNotification(`${action} so‘rovingiz ${outcome}.`);
          if (row) window.setTimeout(() => window.location.reload(), 2800);
        }
      }
      for (const order of data.orders || []) {
        const key = `order-${order.id}`;
        nextStatuses[key] = order.status;
        const status = document.querySelector(`[data-order-status="${order.id}"]`);
        if (status) {
          status.className = `profile-status profile-status--${order.status}`;
          status.querySelector("[data-order-status-label]").textContent = order.label;
        }
        if (previousStatuses[key] && previousStatuses[key] !== order.status) {
          showNotification(`Buyurtma #${order.id} holati: ${order.label.toLowerCase()}.`);
        }
      }
      previousStatuses = nextStatuses;
      hasStatusSnapshot = true;
      try {
        localStorage.setItem(storageKey, JSON.stringify(nextStatuses));
      } catch {}
      const balance = document.querySelector("[data-wallet-balance]");
      if (balance) balance.textContent = Number(data.balance).toLocaleString("uz-UZ");
    } catch {}
  };

  pollTopupStatus();
  window.setInterval(pollTopupStatus, 5000);
}

const imageInput = document.querySelector("#id_image");
const imagePreview = document.querySelector("[data-image-preview]");
const imageName = document.querySelector("[data-image-name]");

imageInput?.addEventListener("change", () => {
  const file = imageInput.files?.[0];
  if (!file || !imagePreview || !file.type.startsWith("image/")) return;

  let preview = imagePreview.querySelector("img");
  if (!preview) {
    preview = document.createElement("img");
    preview.alt = "Tanlangan mahsulot rasmi";
    imagePreview.append(preview);
  }

  preview.src = URL.createObjectURL(file);
  imagePreview.classList.add("has-image");
  if (imageName) imageName.textContent = file.name;
});

const promoCarousel = document.querySelector("[data-promo-carousel]");

if (promoCarousel) {
  const slides = [...promoCarousel.querySelectorAll(".promotion-slide")];
  const dots = [...promoCarousel.querySelectorAll("[data-promo-slide]")];
  let activeSlide = 0;
  let rotationTimer;

  const showSlide = (index) => {
    activeSlide = (index + slides.length) % slides.length;
    slides.forEach((slide, slideIndex) => {
      const isActive = slideIndex === activeSlide;
      slide.classList.toggle("is-active", isActive);
      slide.setAttribute("aria-hidden", String(!isActive));
    });
    dots.forEach((dot, dotIndex) => {
      const isActive = dotIndex === activeSlide;
      dot.classList.toggle("is-active", isActive);
      if (isActive) dot.setAttribute("aria-current", "true");
      else dot.removeAttribute("aria-current");
    });
  };

  const stopRotation = () => window.clearInterval(rotationTimer);
  const startRotation = () => {
    stopRotation();
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      rotationTimer = window.setInterval(() => showSlide(activeSlide + 1), 5000);
    }
  };

  promoCarousel.querySelector("[data-promo-prev]")?.addEventListener("click", () => {
    showSlide(activeSlide - 1);
    startRotation();
  });
  promoCarousel.querySelector("[data-promo-next]")?.addEventListener("click", () => {
    showSlide(activeSlide + 1);
    startRotation();
  });
  dots.forEach((dot) => dot.addEventListener("click", () => {
    showSlide(Number(dot.dataset.promoSlide));
    startRotation();
  }));
  promoCarousel.addEventListener("mouseenter", stopRotation);
  promoCarousel.addEventListener("mouseleave", startRotation);
  promoCarousel.addEventListener("focusin", stopRotation);
  promoCarousel.addEventListener("focusout", (event) => {
    if (!promoCarousel.contains(event.relatedTarget)) startRotation();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopRotation();
    else startRotation();
  });
  startRotation();
}