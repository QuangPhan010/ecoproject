document.addEventListener("DOMContentLoaded", function () {

  const addressInput =
    document.querySelector("#id_address");

  const shippingEl =
    document.getElementById("shipping-cost");

  const totalEl =
    document.getElementById("total-price");

  if (!addressInput) return;

  function format(v) {
    return v.toLocaleString("vi-VN") + "₫";
  }

  async function updateSummary() {

    const address =
      addressInput.value.trim();

    if (address.length < 3)
      return;

    const res =
      await fetch(
        `/shops/api/checkout-summary/?address=${encodeURIComponent(address)}`
      );

    const data =
      await res.json();

    shippingEl.textContent =
      format(data.shipping_cost);

    totalEl.textContent =
      format(data.final_total);

  }

  addressInput.addEventListener(
    "input",
    updateSummary
  );

});
