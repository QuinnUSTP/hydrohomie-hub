(function () {
  "use strict";

  var POLL_MS = 5000;

  var container = document.getElementById("nodes");
  var banner = document.getElementById("alert-banner");
  var updated = document.getElementById("updated");
  var connectionError = document.getElementById("connection-error");
  var emptyMessage = document.getElementById("empty");
  var apiUrl = container.dataset.apiUrl;
  var loginUrl = container.dataset.loginUrl;

  var STATE = {
    alert: { label: "ALERT", card: "border-danger border-2", badge: "text-bg-danger" },
    check: { label: "CHECK", card: "border-warning border-2", badge: "text-bg-warning" },
    offline: { label: "OFFLINE", card: "border-secondary", badge: "text-bg-secondary" },
    normal: { label: "NORMAL", card: "border-success", badge: "text-bg-success" }
  };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }

  function formatTime(iso) {
    if (!iso) { return "never"; }
    return new Date(iso).toLocaleString([], {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit"
    });
  }

  function formatDistance(cm) {
    return cm === null || cm === undefined ? "no echo" : cm.toFixed(1) + " cm";
  }

  function formatFloat(value) {
    if (value === null || value === undefined) { return "-"; }
    return value ? "HIGH" : "normal";
  }

  function row(label, value) {
    var line = el("div", "d-flex justify-content-between");
    line.appendChild(el("span", "text-body-secondary", label));
    line.appendChild(el("span", "fw-semibold", value));
    return line;
  }

  function recentTable(recent) {
    var details = el("details", "mt-2");
    details.appendChild(el("summary", "small text-body-secondary", "Recent readings"));
    var wrap = el("div", "table-responsive");
    var table = el("table", "table table-sm mb-0 small");
    var head = el("tr");
    ["Time", "Distance", "Float"].forEach(function (name) {
      head.appendChild(el("th", "", name));
    });
    var thead = el("thead");
    thead.appendChild(head);
    table.appendChild(thead);
    var body = el("tbody");
    recent.forEach(function (r) {
      var tr = el("tr");
      tr.appendChild(el("td", "text-nowrap", formatTime(r.time)));
      tr.appendChild(el("td", "", formatDistance(r.distance_cm)));
      tr.appendChild(el("td", "", formatFloat(r.float_triggered)));
      body.appendChild(tr);
    });
    table.appendChild(body);
    wrap.appendChild(table);
    details.appendChild(wrap);
    return details;
  }

  function buildCard(node) {
    var style = STATE[node.state] || STATE.normal;
    var col = el("div", "col-12 col-md-6 col-xl-4");
    var card = el("div", "card shadow-sm h-100 " + style.card);
    var body = el("div", "card-body");

    var header = el("div", "d-flex justify-content-between align-items-start mb-2 gap-2");
    var titles = el("div");
    titles.appendChild(el("h2", "h5 mb-0", node.node_id + " - " + node.name));
    if (node.location) { titles.appendChild(el("small", "text-body-secondary", node.location)); }
    header.appendChild(titles);
    header.appendChild(el("span", "badge " + style.badge, style.label));
    body.appendChild(header);

    body.appendChild(row("Water distance", formatDistance(node.distance_cm)));
    body.appendChild(row(
      "Alert level",
      node.alert_distance_cm === null ? "not set" : "<= " + node.alert_distance_cm + " cm"
    ));
    body.appendChild(row("Float switch", formatFloat(node.float_triggered)));
    body.appendChild(row("Last data", formatTime(node.last_seen)));
    if (node.alert_since) { body.appendChild(row("Alert since", formatTime(node.alert_since))); }
    if (node.state === "alert" && !node.online) {
      body.appendChild(el("div", "text-danger small mt-1", "Node is offline. Data may be old."));
    }
    if (node.recent.length) { body.appendChild(recentTable(node.recent)); }

    card.appendChild(body);
    col.appendChild(card);
    return col;
  }

  function openDetails() {
    var open = {};
    container.querySelectorAll("[data-node]").forEach(function (col) {
      var details = col.querySelector("details");
      open[col.dataset.node] = details ? details.open : false;
    });
    return open;
  }

  function render(data) {
    var wasOpen = openDetails();
    container.replaceChildren();

    var alerting = data.nodes.filter(function (n) { return n.state === "alert"; });
    if (alerting.length) {
      banner.textContent = "FLOOD ALERT: " + alerting.map(function (n) {
        return n.name + " (" + n.node_id + ")";
      }).join(", ");
      banner.classList.remove("d-none");
    } else {
      banner.classList.add("d-none");
    }

    emptyMessage.classList.toggle("d-none", data.nodes.length > 0);

    data.nodes.forEach(function (node) {
      var col = buildCard(node);
      col.dataset.node = node.node_id;
      var details = col.querySelector("details");
      if (details && wasOpen[node.node_id]) { details.open = true; }
      container.appendChild(col);
    });

    updated.textContent = "Updated " + new Date().toLocaleTimeString();
  }

  function poll() {
    fetch(apiUrl, {
      credentials: "same-origin",
      headers: { "Accept": "application/json" }
    })
      .then(function (response) {
        if (response.status === 401 || response.status === 403) {
          window.location.href = loginUrl;
          return null;
        }
        if (!response.ok) { throw new Error("HTTP " + response.status); }
        return response.json();
      })
      .then(function (data) {
        if (data) {
          render(data);
          connectionError.classList.add("d-none");
        }
      })
      .catch(function () {
        connectionError.classList.remove("d-none");
      });
  }

  poll();
  setInterval(function () {
    if (document.visibilityState === "visible") { poll(); }
  }, POLL_MS);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") { poll(); }
  });
})();