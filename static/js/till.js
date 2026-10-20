/* SakoraFlow till. Plain JavaScript, no external libraries.
   The server decides prices, VAT and stock; this screen only sends product ids, quantities and payments. */
(function () {
  "use strict";

  var cfg = JSON.parse(document.getElementById("till-config").textContent);
  var csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
  function $(id) { return document.getElementById(id); }

  var products = [];
  var byBarcode = {};
  var cart = [];            // [{p: product, qty: number}]
  var saleUuid = newUuid();  // same value on retries of one sale, so it can never be recorded twice
  var sending = false;
  var cashTouched = false;
  var lastReceiptUrl = "";

  function newUuid() {
    if (window.crypto && crypto.randomUUID) { return crypto.randomUUID(); }
    var b = new Uint8Array(16);
    crypto.getRandomValues(b);
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    var h = Array.prototype.map.call(b, function (x) { return ("0" + x.toString(16)).slice(-2); }).join("");
    return h.slice(0, 8) + "-" + h.slice(8, 12) + "-" + h.slice(12, 16) + "-" + h.slice(16, 20) + "-" + h.slice(20);
  }
  function cartChanged() { saleUuid = newUuid(); renderCart(); }

  function cents(str) {
    var n = parseFloat(String(str).replace(/,/g, ""));
    return isNaN(n) || n < 0 ? 0 : Math.round(n * 100);
  }
  function fmt(c) { return (c / 100).toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  function plain(c) { return (c / 100).toFixed(2); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text !== undefined) { e.textContent = text; }
    return e;
  }
  function setStatus(msg, bad) {
    var s = $("status");
    s.textContent = msg || "";
    s.className = "status" + (bad ? " bad" : "");
  }

  /* ---- Products ---- */
  function loadProducts() {
    return fetch(cfg.productsUrl, { credentials: "same-origin" })
      .then(function (r) { if (!r.ok) { throw new Error(r.status); } return r.json(); })
      .then(function (data) {
        products = data.products;
        byBarcode = {};
        products.forEach(function (p) {
          p.lname = p.name.toLowerCase();
          p.cents = cents(p.price);
          if (p.barcode) { byBarcode[p.barcode] = p; }
        });
        renderResults();
      })
      .catch(function () { setStatus("Could not load products. Check the internet and reload.", true); });
  }

  function search(q) {
    q = q.trim().toLowerCase();
    if (!q) { return products.slice(0, 24); }
    var words = q.split(/\s+/);
    return products.filter(function (p) {
      if (p.barcode && p.barcode.indexOf(q) === 0) { return true; }
      return words.every(function (w) { return p.lname.indexOf(w) !== -1; });
    }).slice(0, 30);
  }

  function renderResults() {
    var box = $("results");
    box.textContent = "";
    search($("scan").value).forEach(function (p) {
      var b = el("button", "tile-btn");
      b.type = "button";
      b.appendChild(el("span", "n", p.name));
      var m = el("span", "m", fmt(p.cents) + "  ·  ");
      var stock = el("span", p.stock <= 0 ? "low" : "", p.stock <= 0 ? "out of stock" : "stock " + p.stock);
      m.appendChild(stock);
      b.appendChild(m);
      b.addEventListener("click", function () { addToCart(p, 1); });
      box.appendChild(b);
    });
  }

  /* ---- Cart ---- */
  function lineCents(l) { return Math.round(l.p.cents * l.qty); }
  function totalCents() { return cart.reduce(function (s, l) { return s + lineCents(l); }, 0); }

  function addToCart(p, qty) {
    var found = cart.filter(function (l) { return l.p.id === p.id; })[0];
    if (found) { found.qty = Math.round((found.qty + qty) * 1000) / 1000; }
    else { cart.push({ p: p, qty: qty }); }
    setStatus("Added: " + p.name);
    $("scan").value = "";
    cartChanged();
    renderResults();
    $("scan").focus();
  }

  function setQty(i, qty) {
    if (!(qty > 0)) { cart.splice(i, 1); }
    else { cart[i].qty = Math.round(qty * 1000) / 1000; }
    cartChanged();
  }

  function renderCart() {
    var body = $("cart-body");
    body.textContent = "";
    if (!cart.length) {
      var tr = el("tr");
      var td = el("td", "cart-empty", "Scan or tap a product to start.");
      td.colSpan = 4;
      tr.appendChild(td);
      body.appendChild(tr);
    }
    cart.forEach(function (l, i) {
      var tr = el("tr");
      var name = el("td");
      name.appendChild(el("div", "", l.p.name));
      name.appendChild(el("small", "", fmt(l.p.cents) + " each"));
      var qtyTd = el("td");
      var q = el("div", "qty");
      var minus = el("button", "", "−"); minus.type = "button";
      var plus = el("button", "", "+"); plus.type = "button";
      var input = el("input"); input.type = "number"; input.step = "any"; input.min = "0"; input.value = l.qty;
      minus.addEventListener("click", function () { setQty(i, l.qty - 1); });
      plus.addEventListener("click", function () { setQty(i, l.qty + 1); });
      input.addEventListener("change", function () { setQty(i, parseFloat(input.value)); });
      q.appendChild(minus); q.appendChild(input); q.appendChild(plus);
      qtyTd.appendChild(q);
      var tot = el("td", "num", fmt(lineCents(l)));
      var rm = el("td");
      var x = el("button", "ghost mini", "×"); x.type = "button"; x.title = "Remove";
      x.addEventListener("click", function () { setQty(i, 0); });
      rm.appendChild(x);
      [name, qtyTd, tot, rm].forEach(function (c) { tr.appendChild(c); });
      body.appendChild(tr);
    });
    $("total").textContent = fmt(totalCents());
    $("pay-btn").disabled = !cart.length;
  }

  function handleEnter() {
    var raw = $("scan").value.trim();
    if (!raw) { if (cart.length) { openPay(); } return; }
    var qty = 1, code = raw;
    var m = raw.match(/^(\d+(?:\.\d{1,3})?)\s*\*\s*(.+)$/);   // e.g. 3*6161100123456
    if (m) { qty = parseFloat(m[1]); code = m[2].trim(); }
    var p = byBarcode[code];
    if (!p) {
      var r = search(code);
      if (r.length === 1) { p = r[0]; }
      else if (r.length > 1) { setStatus("Several matches. Tap the right product.", false); return; }
    }
    if (!p) { setStatus("No product found for \"" + code + "\".", true); $("scan").select(); return; }
    addToCart(p, qty);
  }

  /* ---- Payment ---- */
  function nonCash() { return cents($("mpesa-amt").value) + cents($("card-amt").value) + cents($("bank-amt").value); }

  function validate(total, nc, due, cash) {
    if (nc > total) { return "M-Pesa, card and bank amounts are more than the total."; }
    if (cash < due) { return "Cash received is short by " + fmt(due - cash) + "."; }
    if (due === 0 && cash > 0) { return "The sale is fully paid. Clear the cash amount."; }
    if (cents($("mpesa-amt").value) > 0 && !/^[A-Z0-9]{10}$/.test($("mpesa-code").value)) {
      return "Enter the 10-character M-Pesa code.";
    }
    return "";
  }

  function updatePay() {
    var total = totalCents(), nc = nonCash();
    if (!cashTouched) { $("cash-amt").value = nc >= total ? "" : plain(total - nc); }
    var due = Math.max(0, total - nc), cash = cents($("cash-amt").value);
    $("cash-due").textContent = fmt(due);
    $("change").textContent = fmt(Math.max(0, cash - due));
    var problem = validate(total, nc, due, cash);
    $("pay-hint").textContent = problem;
    $("pay-confirm").disabled = !!problem || sending;
  }

  function openPay() {
    if (!cart.length) { return; }
    ["mpesa-amt", "mpesa-code", "card-amt", "card-ref", "bank-amt", "bank-ref"].forEach(function (id) { $(id).value = ""; });
    cashTouched = false;
    $("pay-total").textContent = fmt(totalCents());
    $("pay-error").textContent = "";
    $("pay-modal").hidden = false;
    updatePay();
    $("cash-amt").focus();
    $("cash-amt").select();
  }
  function closePay() { $("pay-modal").hidden = true; $("scan").focus(); }

  function fill(kind) {
    var total = totalCents();
    if (kind === "cash") {
      cashTouched = true;
      $("cash-amt").value = plain(Math.max(0, total - nonCash()));
    } else {
      var own = cents($(kind + "-amt").value);
      var others = nonCash() - own;
      $(kind + "-amt").value = plain(Math.max(0, total - others));
      cashTouched = false;
    }
    updatePay();
  }

  function confirmSale() {
    if (sending) { return; }
    var payments = [];
    var cash = cents($("cash-amt").value);
    if (cash > 0) { payments.push({ method: "cash", amount: plain(cash) }); }
    [["mpesa", "mpesa-amt", "mpesa-code"], ["card", "card-amt", "card-ref"], ["bank", "bank-amt", "bank-ref"]].forEach(function (m) {
      var a = cents($(m[1]).value);
      if (a > 0) { payments.push({ method: m[0], amount: plain(a), reference: $(m[2]).value.trim() }); }
    });
    var body = {
      uuid: saleUuid,
      items: cart.map(function (l) { return { product_id: l.p.id, quantity: String(l.qty) }; }),
      payments: payments
    };
    sending = true;
    $("pay-error").textContent = "";
    updatePay();
    fetch(cfg.saleUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify(body)
    })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (data) { return { data: data }; });
      })
      .then(function (res) {
        sending = false;
        if (res.data && res.data.ok) { saleDone(res.data); }
        else {
          $("pay-error").textContent = (res.data && res.data.error) || "The sale could not be saved. Try again.";
          updatePay();
        }
      })
      .catch(function () {
        sending = false;
        $("pay-error").textContent = "No connection. Nothing was confirmed. Check the internet, then press Complete sale again.";
        updatePay();
      });
  }

  function printReceipt(url) {
    var old = $("print-frame");
    if (old) { old.parentNode.removeChild(old); }
    var f = el("iframe", "print-frame");
    f.id = "print-frame";
    f.src = url + "?autoprint=1";
    document.body.appendChild(f);
  }

  function saleDone(d) {
    $("pay-modal").hidden = true;
    lastReceiptUrl = d.receipt_url;
    $("done-receipt").textContent = d.receipt_no + "  ·  Total " + fmt(cents(d.total)) +
      (d.created === false ? "  (already recorded)" : "");
    $("done-change").textContent = fmt(cents(d.change));
    $("done-modal").hidden = false;
    printReceipt(lastReceiptUrl);
    cart = [];
    cartChanged();
    loadProducts();
    $("done-new").focus();
  }
  function closeDone() { $("done-modal").hidden = true; setStatus(""); $("scan").focus(); }

  /* ---- Wiring ---- */
  $("scan").addEventListener("input", renderResults);
  $("scan").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); handleEnter(); }
    else if (e.key === "Escape") { $("scan").value = ""; renderResults(); }
  });
  $("pay-btn").addEventListener("click", openPay);
  $("clear-btn").addEventListener("click", function () {
    if (cart.length && window.confirm("Clear this sale?")) { cart = []; cartChanged(); }
    $("scan").focus();
  });
  $("pay-cancel").addEventListener("click", closePay);
  $("pay-confirm").addEventListener("click", confirmSale);
  $("done-new").addEventListener("click", closeDone);
  $("done-print").addEventListener("click", function () { if (lastReceiptUrl) { printReceipt(lastReceiptUrl); } });

  ["cash-amt", "mpesa-amt", "card-amt", "bank-amt", "mpesa-code", "card-ref", "bank-ref"].forEach(function (id) {
    $(id).addEventListener("input", function () {
      if (id === "cash-amt") { cashTouched = true; }
      if (id === "mpesa-code") { this.value = this.value.toUpperCase().replace(/[^A-Z0-9]/g, ""); }
      updatePay();
    });
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-fill]"), function (b) {
    b.addEventListener("click", function () { fill(b.getAttribute("data-fill")); });
  });

  document.addEventListener("keydown", function (e) {
    if (!$("done-modal").hidden) {
      if (e.key === "Enter") { e.preventDefault(); closeDone(); }
      return;
    }
    if (!$("pay-modal").hidden) {
      if (e.key === "Escape") { closePay(); }
      else if (e.key === "Enter" && e.target.tagName === "INPUT" && !$("pay-confirm").disabled) {
        e.preventDefault();
        confirmSale();
      }
      return;
    }
    if (e.key === "F2") { e.preventDefault(); openPay(); }
  });

  renderCart();
  loadProducts();
  $("scan").focus();
})();
