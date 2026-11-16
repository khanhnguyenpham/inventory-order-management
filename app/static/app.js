const state = {
  token: localStorage.getItem("khogon_token"),
  user: null,
  products: [],
  orders: [],
  movements: [],
  overview: null,
};

const currency = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND", maximumFractionDigits: 0 });
const number = new Intl.NumberFormat("vi-VN");
const dateTime = new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" });
const shortDate = new Intl.DateTimeFormat("vi-VN", { weekday: "short", day: "2-digit", month: "2-digit" });

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function idempotencyKey(prefix) {
  const random = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}:${random}`;
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(path, { ...options, headers });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/auth/login") logout(false);
    const message = payload?.error?.message || payload?.detail || "Không thể hoàn tất yêu cầu";
    throw new Error(Array.isArray(message) ? "Dữ liệu nhập chưa hợp lệ" : message);
  }
  return payload;
}

function toast(message, type = "success") {
  const region = document.querySelector("#toast-region");
  const item = document.createElement("div");
  item.className = `toast ${type === "error" ? "error" : ""}`;
  item.textContent = message;
  region.append(item);
  setTimeout(() => item.remove(), 3500);
}

function setLoading(button, loading, label = "Đang xử lý…") {
  if (!button.dataset.label) button.dataset.label = button.textContent;
  button.disabled = loading;
  button.textContent = loading ? label : button.dataset.label;
}

async function login(event) {
  event.preventDefault();
  const button = document.querySelector("#login-submit");
  const error = document.querySelector("#login-error");
  error.textContent = "";
  setLoading(button, true, "Đang đăng nhập…");
  try {
    const payload = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: document.querySelector("#login-email").value.trim(),
        password: document.querySelector("#login-password").value,
      }),
    });
    state.token = payload.access_token;
    state.user = payload.user;
    localStorage.setItem("khogon_token", state.token);
    await enterApplication();
  } catch (requestError) {
    error.textContent = requestError.message;
  } finally {
    setLoading(button, false);
  }
}

function logout(showMessage = true) {
  state.token = null;
  state.user = null;
  localStorage.removeItem("khogon_token");
  document.querySelector("#app-shell").hidden = true;
  document.querySelector("#login-page").hidden = false;
  if (showMessage) toast("Đã đăng xuất khỏi hệ thống");
}

async function enterApplication() {
  document.querySelector("#login-page").hidden = true;
  document.querySelector("#app-shell").hidden = false;
  updateUserSummary();
  await refreshAll();
  showView(location.hash.slice(1) || "dashboard");
}

function updateUserSummary() {
  const initials = state.user.full_name
    .split(" ")
    .slice(-2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
  document.querySelector("#user-avatar").textContent = initials;
  document.querySelector("#user-name").textContent = state.user.full_name;
  document.querySelector("#user-role").textContent = state.user.role === "manager" ? "Quản lý" : "Nhân viên";
  document.querySelectorAll(".manager-only").forEach((element) => {
    element.hidden = state.user.role !== "manager";
  });
}

async function refreshAll() {
  try {
    const [overview, products, orders, movements] = await Promise.all([
      api("/api/reports/overview"),
      api("/api/products"),
      api("/api/orders?limit=100"),
      api("/api/inventory/movements?limit=100"),
    ]);
    state.overview = overview;
    state.products = products;
    state.orders = orders;
    state.movements = movements;
    renderDashboard();
    renderProducts();
    renderOrders();
    renderMovements();
    updateProductSelects();
    if (state.user.role === "manager") await renderAudit();
  } catch (requestError) {
    toast(requestError.message, "error");
  }
}

function renderDashboard() {
  const overview = state.overview;
  document.querySelector("#metric-value").textContent = currency.format(overview.inventory_value_vnd);
  document.querySelector("#metric-orders").textContent = number.format(overview.order_count);
  document.querySelector("#metric-revenue").textContent = `${currency.format(overview.revenue_vnd)} doanh thu`;
  document.querySelector("#metric-low-stock").textContent = number.format(overview.low_stock_count);
  document.querySelector("#metric-units").textContent = number.format(overview.stock_units);
  document.querySelector("#metric-products").textContent = `${number.format(overview.product_count)} sản phẩm đang hoạt động`;

  const weekRevenue = overview.sales_by_day.reduce((total, item) => total + item.revenue_vnd, 0);
  document.querySelector("#week-revenue").textContent = currency.format(weekRevenue);
  const maximum = Math.max(...overview.sales_by_day.map((item) => item.revenue_vnd), 1);
  document.querySelector("#sales-chart").innerHTML = overview.sales_by_day
    .map((item) => {
      const height = item.revenue_vnd ? Math.max(8, Math.round((item.revenue_vnd / maximum) * 100)) : 3;
      const label = shortDate.format(new Date(`${item.day}T12:00:00`));
      return `<div class="bar-column" title="${escapeHtml(label)}: ${currency.format(item.revenue_vnd)}">
        <i style="height:${height}%"></i><span>${escapeHtml(label)}</span>
      </div>`;
    })
    .join("");

  const lowStock = state.products.filter((product) => product.is_low_stock).slice(0, 5);
  document.querySelector("#low-stock-list").innerHTML = lowStock.length
    ? lowStock
        .map(
          (product) => `<div class="attention-item">
            <strong>${escapeHtml(product.name)}</strong><span>${number.format(product.stock_quantity)} ${escapeHtml(product.unit)}</span>
            <small>${escapeHtml(product.sku)} · Ngưỡng ${number.format(product.reorder_level)}</small>
          </div>`,
        )
        .join("")
    : '<p class="empty-state">Không có sản phẩm nào chạm ngưỡng nhập.</p>';

  renderOrderRows(document.querySelector("#recent-orders-body"), state.orders.slice(0, 6), false);
}

function renderProducts() {
  const query = document.querySelector("#product-search")?.value.trim().toLowerCase() || "";
  const lowOnly = document.querySelector("#low-stock-filter")?.checked || false;
  const products = state.products.filter((product) => {
    const matchesQuery = [product.sku, product.name, product.category].some((value) =>
      value.toLowerCase().includes(query),
    );
    return matchesQuery && (!lowOnly || product.is_low_stock);
  });
  document.querySelector("#products-body").innerHTML = products.length
    ? products
        .map(
          (product) => `<tr>
            <td class="product-cell"><strong>${escapeHtml(product.name)}</strong><span>${escapeHtml(product.sku)}</span></td>
            <td>${escapeHtml(product.category)}</td>
            <td>${currency.format(product.price_vnd)}</td>
            <td><strong>${number.format(product.stock_quantity)}</strong> ${escapeHtml(product.unit)}</td>
            <td>${number.format(product.reorder_level)} ${escapeHtml(product.unit)}</td>
            <td><span class="status-pill ${product.is_low_stock ? "warning" : ""}">${product.is_low_stock ? "Cần nhập" : "Ổn định"}</span></td>
          </tr>`,
        )
        .join("")
    : '<tr><td class="empty-state" colspan="6">Không tìm thấy sản phẩm phù hợp.</td></tr>';
}

function renderOrders() {
  renderOrderRows(document.querySelector("#orders-body"), state.orders, true);
}

function renderOrderRows(container, orders, showActions) {
  container.innerHTML = orders.length
    ? orders
        .map(
          (order) => `<tr>
            <td><strong>${escapeHtml(order.order_code)}</strong></td>
            <td>${escapeHtml(order.customer_name)}</td>
            ${showActions ? `<td>${escapeHtml(order.created_by_name)}</td><td>${dateTime.format(new Date(`${order.created_at}Z`))}</td>` : ""}
            ${showActions ? "" : `<td>${number.format(order.item_count)}</td>`}
            <td><span class="status-pill ${order.status === "CANCELLED" ? "cancelled" : ""}">${order.status === "CONFIRMED" ? "Đã xác nhận" : "Đã hủy"}</span></td>
            <td><strong>${currency.format(order.total_vnd)}</strong></td>
            ${showActions ? `<td>${state.user.role === "manager" && order.status === "CONFIRMED" ? `<button class="text-button cancel-order" data-order-id="${order.id}" type="button">Hủy đơn</button>` : ""}</td>` : ""}
          </tr>`,
        )
        .join("")
    : `<tr><td class="empty-state" colspan="${showActions ? 7 : 5}">Chưa có đơn hàng.</td></tr>`;
}

function renderMovements() {
  document.querySelector("#movements-body").innerHTML = state.movements.length
    ? state.movements
        .map(
          (movement) => `<tr>
            <td>${dateTime.format(new Date(`${movement.created_at}Z`))}</td>
            <td class="product-cell"><strong>${escapeHtml(movement.product_name)}</strong><span>${escapeHtml(movement.sku)}</span></td>
            <td>${movement.movement_type === "IN" ? "Nhập" : movement.movement_type === "OUT" ? "Xuất" : "Điều chỉnh"}</td>
            <td class="${movement.quantity_change > 0 ? "quantity-positive" : "quantity-negative"}">${movement.quantity_change > 0 ? "+" : ""}${number.format(movement.quantity_change)}</td>
            <td>${number.format(movement.stock_after)}</td>
            <td>${escapeHtml(movement.reference || "—")}</td>
            <td>${escapeHtml(movement.created_by_name)}</td>
          </tr>`,
        )
        .join("")
    : '<tr><td class="empty-state" colspan="7">Chưa có giao dịch nhập hoặc xuất kho.</td></tr>';
}

async function renderAudit() {
  const logs = await api("/api/audit-logs?limit=100");
  const labels = {
    PRODUCT_CREATED: "Tạo sản phẩm",
    PRODUCT_UPDATED: "Cập nhật sản phẩm",
    STOCK_CHANGED: "Thay đổi tồn kho",
    ORDER_CREATED: "Tạo đơn hàng",
    ORDER_CANCELLED: "Hủy đơn hàng",
  };
  document.querySelector("#audit-body").innerHTML = logs.length
    ? logs
        .map(
          (log) => `<tr>
            <td>${dateTime.format(new Date(`${log.created_at}Z`))}</td>
            <td>${escapeHtml(log.actor_name)}</td>
            <td><strong>${escapeHtml(labels[log.action] || log.action)}</strong></td>
            <td>${escapeHtml(log.entity_type)} #${escapeHtml(log.entity_id)}</td>
            <td title="${escapeHtml(JSON.stringify(log.detail))}">${escapeHtml(summarizeDetail(log.detail))}</td>
          </tr>`,
        )
        .join("")
    : '<tr><td class="empty-state" colspan="5">Chưa có sự kiện cần ghi nhận.</td></tr>';
}

function summarizeDetail(detail) {
  if (detail.order_code) return detail.order_code;
  if (detail.sku) return detail.sku;
  if (detail.quantity_change) return `${detail.quantity_change > 0 ? "+" : ""}${detail.quantity_change} đơn vị`;
  return Object.keys(detail).slice(0, 3).join(", ") || "—";
}

function updateProductSelects() {
  const options = state.products
    .filter((product) => product.is_active)
    .map(
      (product) => `<option value="${product.id}" data-price="${product.price_vnd}">${escapeHtml(product.name)} · còn ${number.format(product.stock_quantity)} ${escapeHtml(product.unit)}</option>`,
    )
    .join("");
  document.querySelectorAll("[data-product-select]").forEach((select) => {
    select.innerHTML = `<option value="">Chọn sản phẩm</option>${options}`;
  });
}

function showView(viewName) {
  const requested = document.querySelector(`#view-${CSS.escape(viewName)}`);
  const view = requested && !(viewName === "audit" && state.user?.role !== "manager") ? viewName : "dashboard";
  document.querySelectorAll(".view").forEach((element) => element.classList.toggle("active", element.id === `view-${view}`));
  document.querySelectorAll(".nav-item").forEach((element) => element.classList.toggle("active", element.dataset.view === view));
  document.querySelector(".sidebar").classList.remove("open");
  location.hash = view;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function openDialog(id) {
  const dialog = document.querySelector(`#${id}`);
  if (id === "movement-dialog") updateProductSelects();
  if (id === "order-dialog") {
    document.querySelector("#order-lines").innerHTML = "";
    addOrderLine();
    calculateOrderTotal();
  }
  dialog.showModal();
}

function addOrderLine() {
  const fragment = document.querySelector("#order-line-template").content.cloneNode(true);
  const row = fragment.querySelector(".order-line");
  const select = row.querySelector(".order-product");
  select.innerHTML = `<option value="">Chọn sản phẩm</option>${state.products
    .filter((product) => product.is_active && product.stock_quantity > 0)
    .map(
      (product) => `<option value="${product.id}" data-price="${product.price_vnd}" data-stock="${product.stock_quantity}">${escapeHtml(product.name)} · còn ${number.format(product.stock_quantity)}</option>`,
    )
    .join("")}`;
  row.querySelectorAll("select, input").forEach((element) => element.addEventListener("input", calculateOrderTotal));
  row.querySelector(".remove-line").addEventListener("click", () => {
    if (document.querySelectorAll(".order-line").length > 1) row.remove();
    calculateOrderTotal();
  });
  document.querySelector("#order-lines").append(fragment);
}

function calculateOrderTotal() {
  let total = 0;
  document.querySelectorAll(".order-line").forEach((row) => {
    const option = row.querySelector(".order-product").selectedOptions[0];
    const quantity = Number(row.querySelector(".order-quantity").value || 0);
    const lineTotal = Number(option?.dataset.price || 0) * quantity;
    row.querySelector(".order-line-total").textContent = currency.format(lineTotal);
    total += lineTotal;
  });
  document.querySelector("#order-total-value").textContent = currency.format(total);
}

async function submitProduct(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const error = form.querySelector("[data-form-error]");
  const data = new FormData(form);
  error.textContent = "";
  setLoading(button, true);
  try {
    await api("/api/products", {
      method: "POST",
      body: JSON.stringify({
        sku: data.get("sku"),
        name: data.get("name"),
        category: data.get("category"),
        unit: data.get("unit"),
        price_vnd: Number(data.get("price_vnd")),
        stock_quantity: Number(data.get("stock_quantity")),
        reorder_level: Number(data.get("reorder_level")),
      }),
    });
    form.closest("dialog").close();
    form.reset();
    toast("Đã thêm sản phẩm vào danh mục");
    await refreshAll();
  } catch (requestError) {
    error.textContent = requestError.message;
  } finally {
    setLoading(button, false);
  }
}

async function submitMovement(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const error = form.querySelector("[data-form-error]");
  const data = new FormData(form);
  error.textContent = "";
  setLoading(button, true);
  try {
    await api("/api/inventory/movements", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey("movement") },
      body: JSON.stringify({
        product_id: Number(data.get("product_id")),
        movement_type: data.get("movement_type"),
        quantity: Number(data.get("quantity")),
        adjustment_direction: data.get("movement_type") === "ADJUST" ? data.get("adjustment_direction") : null,
        reference: data.get("reference") || null,
        note: data.get("note") || null,
      }),
    });
    form.closest("dialog").close();
    form.reset();
    toast("Đã cập nhật tồn kho");
    await refreshAll();
  } catch (requestError) {
    error.textContent = requestError.message;
  } finally {
    setLoading(button, false);
  }
}

async function submitOrder(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const error = form.querySelector("[data-form-error]");
  const data = new FormData(form);
  const items = [...document.querySelectorAll(".order-line")].map((row) => ({
    product_id: Number(row.querySelector(".order-product").value),
    quantity: Number(row.querySelector(".order-quantity").value),
  }));
  if (items.some((item) => !item.product_id || !item.quantity)) {
    error.textContent = "Vui lòng chọn sản phẩm và số lượng cho mọi dòng.";
    return;
  }
  error.textContent = "";
  setLoading(button, true);
  try {
    const order = await api("/api/orders", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey("order") },
      body: JSON.stringify({
        customer_name: data.get("customer_name"),
        customer_phone: data.get("customer_phone") || null,
        items,
      }),
    });
    form.closest("dialog").close();
    form.reset();
    toast(`Đã tạo đơn ${order.order_code}`);
    await refreshAll();
  } catch (requestError) {
    error.textContent = requestError.message;
  } finally {
    setLoading(button, false);
  }
}

async function cancelOrder(orderId) {
  if (!window.confirm("Hủy đơn sẽ hoàn lại toàn bộ số lượng vào kho. Bạn muốn tiếp tục?")) return;
  try {
    const order = await api(`/api/orders/${orderId}/cancel`, { method: "POST" });
    toast(`Đã hủy ${order.order_code} và hoàn lại tồn kho`);
    await refreshAll();
  } catch (requestError) {
    toast(requestError.message, "error");
  }
}

function bindEvents() {
  document.querySelector("#login-form").addEventListener("submit", login);
  document.querySelector("#logout-button").addEventListener("click", () => logout());
  document.querySelector("#mobile-menu-button").addEventListener("click", () => document.querySelector(".sidebar").classList.toggle("open"));
  document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
  document.querySelectorAll("[data-view-jump]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.viewJump)));
  document.querySelectorAll("[data-open]").forEach((button) => button.addEventListener("click", () => openDialog(button.dataset.open)));
  document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => button.closest("dialog").close()));
  document.querySelectorAll("dialog").forEach((dialog) => dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  }));
  document.querySelector("#product-search").addEventListener("input", renderProducts);
  document.querySelector("#low-stock-filter").addEventListener("change", renderProducts);
  document.querySelector("#product-form").addEventListener("submit", submitProduct);
  document.querySelector("#movement-form").addEventListener("submit", submitMovement);
  document.querySelector("#order-form").addEventListener("submit", submitOrder);
  document.querySelector("#add-order-line").addEventListener("click", addOrderLine);
  document.querySelector("#movement-type").addEventListener("change", (event) => {
    document.querySelector("#adjustment-direction-field").hidden = event.target.value !== "ADJUST";
  });
  document.addEventListener("click", (event) => {
    const cancelButton = event.target.closest(".cancel-order");
    if (cancelButton) cancelOrder(cancelButton.dataset.orderId);
  });
  window.addEventListener("hashchange", () => {
    if (state.user) showView(location.hash.slice(1) || "dashboard");
  });
}

async function initialize() {
  bindEvents();
  if (!state.token) return;
  try {
    state.user = await api("/api/auth/me");
    await enterApplication();
  } catch {
    logout(false);
  }
}

initialize();
