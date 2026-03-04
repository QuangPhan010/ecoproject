document.addEventListener("DOMContentLoaded", function () {
  const addressInput =
    document.querySelector("#id_address");
  const shippingEl =
    document.getElementById("shipping-cost");
  const totalEl =
    document.getElementById("total-price");
  const distanceEl =
    document.getElementById("shipping-distance");
  const shippingLoadingEl =
    document.getElementById("shipping-loading");

  if (!addressInput || !shippingEl || !totalEl) return;

  function format(v) {
    return v.toLocaleString("vi-VN") + "₫";
  }

  function setLoading(isLoading) {
    if (!shippingLoadingEl) return;
    shippingLoadingEl.classList.toggle("d-none", !isLoading);
  }

  let debounceTimer = null;
  let requestSeq = 0;

  async function updateSummary() {
    const address =
      addressInput.value.trim();

    if (address.length < 3) {
      setLoading(false);
      return;
    }

    requestSeq += 1;
    const currentSeq = requestSeq;
    setLoading(true);

    try {
      const res =
        await fetch(
          `/shops/api/checkout-summary/?address=${encodeURIComponent(address)}`
        );

      if (!res.ok) return;

      const data =
        await res.json();

      // Ignore stale responses when user types quickly.
      if (currentSeq !== requestSeq) return;

      shippingEl.textContent =
        format(data.shipping_cost);

      const distance =
        Number(data.distance);

      if (distanceEl) {
        if (Number.isFinite(distance) && distance > 0) {
          distanceEl.textContent = `(${distance.toFixed(2)} km)`;
          distanceEl.classList.remove("d-none");
        } else {
          distanceEl.classList.add("d-none");
        }
      }

      totalEl.textContent =
        format(data.final_total);
    } catch (_error) {
      // Keep existing values if API is temporarily unavailable.
    } finally {
      if (currentSeq === requestSeq) {
        setLoading(false);
      }
    }
  }

  function debouncedUpdateSummary() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(updateSummary, 450);
  }

  addressInput.addEventListener(
    "input",
    debouncedUpdateSummary
  );
});
