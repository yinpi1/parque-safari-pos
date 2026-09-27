/**
 * PARQUE SAFARI - SISTEMA WEB DE VENTAS POS
 * Interactividad táctil y motor de carrito demostrativo
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Reloj en tiempo real en la barra superior
    initLiveClock();

    // 2. Si estamos en la pantalla del POS, inicializar el motor de venta
    if (document.getElementById('posCartItems')) {
        initPosEngine();
    }

    // 3. Inicializar interactividad de Cocina KDS y Bar BDS si existen
    initKdsInteractive();

    // 4. Inicializar filtros de tablas y reportes
    initSearchFilters();
});

/* ==========================================================================
   1. RELOJ DIGITAL EN VIVO
   ========================================================================== */
function initLiveClock() {
    const clockEl = document.getElementById('liveClock');
    if (!clockEl) return;

    function update() {
        const now = new Date();
        const hours = String(now.getHours()).padStart(2, '0');
        const minutes = String(now.getMinutes()).padStart(2, '0');
        const seconds = String(now.getSeconds()).padStart(2, '0');
        clockEl.textContent = `${hours}:${minutes}:${seconds}`;
    }

    update();
    setInterval(update, 1000);
}

/* ==========================================================================
   2. MOTOR DE CARRITO POS (Simulación Táctil Interactiva)
   ========================================================================== */
let cart = [];
let modalidad = 'BAR'; // 'BAR' o 'MESA'
let mesaSeleccionada = null;

function initPosEngine() {
    // Escuchar clicks en tarjetas de productos
    const productCards = document.querySelectorAll('.pos-product-card');
    productCards.forEach(card => {
        card.addEventListener('click', () => {
            const id = parseInt(card.dataset.id);
            const nombre = card.dataset.nombre;
            const precio = parseInt(card.dataset.precio);
            const destino = card.dataset.destino;
            const tipo = card.dataset.tipo;

            addToCart({ id, nombre, precio, destino, tipo });
        });
    });

    // Selector de Modalidad BAR vs MESA
    const btnBar = document.getElementById('btnModBar');
    const btnMesa = document.getElementById('btnModMesa');
    const mesaSelectorWrapper = document.getElementById('mesaSelectorWrapper');

    if (btnBar && btnMesa) {
        btnBar.addEventListener('click', () => {
            modalidad = 'BAR';
            mesaSeleccionada = null;
            btnBar.classList.add('active');
            btnMesa.classList.remove('active');
            if (mesaSelectorWrapper) mesaSelectorWrapper.style.display = 'none';
        });

        btnMesa.addEventListener('click', () => {
            modalidad = 'MESA';
            btnMesa.classList.add('active');
            btnBar.classList.remove('active');
            if (mesaSelectorWrapper) mesaSelectorWrapper.style.display = 'flex';
            
            // Si aún no hay mesa elegida, abrir selector
            if (!mesaSeleccionada) {
                const mesaModalEl = document.getElementById('modalSeleccionMesa');
                if (mesaModalEl && typeof bootstrap !== 'undefined') {
                    const modal = new bootstrap.Modal(mesaModalEl);
                    modal.show();
                }
            }
        });
    }

    // Botones para elegir mesa en el modal
    const mesaOptions = document.querySelectorAll('.mesa-option-btn');
    mesaOptions.forEach(btn => {
        btn.addEventListener('click', () => {
            mesaSeleccionada = btn.dataset.mesaNum;
            const mesaLabel = document.getElementById('selectedMesaLabel');
            if (mesaLabel) mesaLabel.textContent = mesaSeleccionada;

            // Cerrar modal
            const mesaModalEl = document.getElementById('modalSeleccionMesa');
            if (mesaModalEl && typeof bootstrap !== 'undefined') {
                const modal = bootstrap.Modal.getInstance(mesaModalEl);
                if (modal) modal.hide();
            }
        });
    });

    // Filtros de categoría en catálogo
    const catButtons = document.querySelectorAll('.pos-cat-btn');
    catButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            catButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const catId = btn.dataset.cat;
            filterProductsByCategory(catId);
        });
    });

    // Búsqueda en catálogo
    const searchInput = document.getElementById('posSearchInput');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase().trim();
            filterProductsByQuery(query);
        });
    }

    // Botón Limpiar Carrito
    const btnClearCart = document.getElementById('btnClearCart');
    if (btnClearCart) {
        btnClearCart.addEventListener('click', () => {
            if (cart.length === 0) return;
            cart = [];
            renderCart();
        });
    }

    // Botón Cobrar / Confirmar Venta
    const btnCheckout = document.getElementById('btnCheckout');
    if (btnCheckout) {
        btnCheckout.addEventListener('click', () => {
            if (cart.length === 0) {
                alert('El carrito está vacío. Agregue al menos un producto para continuar.');
                return;
            }

            if (modalidad === 'MESA' && !mesaSeleccionada) {
                alert('Por favor seleccione una mesa para el pedido.');
                const mesaModalEl = document.getElementById('modalSeleccionMesa');
                if (mesaModalEl && typeof bootstrap !== 'undefined') {
                    const modal = new bootstrap.Modal(mesaModalEl);
                    modal.show();
                }
                return;
            }

            openConfirmModal();
        });
    }

    // Botón dentro del modal de confirmación: Emitir Venta
    const btnFinalizarVenta = document.getElementById('btnFinalizarVenta');
    if (btnFinalizarVenta) {
        btnFinalizarVenta.addEventListener('click', () => {
            // Cerrar modal confirmación
            const modalConfEl = document.getElementById('modalConfirmarVenta');
            if (modalConfEl && typeof bootstrap !== 'undefined') {
                const modalConf = bootstrap.Modal.getInstance(modalConfEl);
                if (modalConf) modalConf.hide();
            }

            // Abrir modal de ticket y comandas
            showTicketModal();
        });
    }

    // Render inicial
    renderCart();
}

function addToCart(item) {
    const existing = cart.find(x => x.id === item.id);
    if (existing) {
        existing.cantidad += 1;
    } else {
        cart.push({
            ...item,
            cantidad: 1
        });
    }
    renderCart();
}

function updateQuantity(id, delta) {
    const item = cart.find(x => x.id === id);
    if (!item) return;

    item.cantidad += delta;
    if (item.cantidad <= 0) {
        cart = cart.filter(x => x.id !== id);
    }
    renderCart();
}

function removeFromCart(id) {
    cart = cart.filter(x => x.id !== id);
    renderCart();
}

function formatCLP(amount) {
    return '$' + amount.toLocaleString('es-CL');
}

function renderCart() {
    const container = document.getElementById('posCartItems');
    const subtotalEl = document.getElementById('cartSubtotal');
    const totalEl = document.getElementById('cartTotal');
    const countBadge = document.getElementById('cartItemsCount');
    const notesInput = document.getElementById('orderNotes');

    if (!container) return;

    if (cart.length === 0) {
        container.innerHTML = `
            <div class="pos-cart-empty">
                <i class="bi bi-cart-x"></i>
                <p class="mb-0 fw-semibold">Carrito de venta vacío</p>
                <small class="text-secondary">Toque los productos para agregarlos al pedido</small>
            </div>
        `;
        if (subtotalEl) subtotalEl.textContent = '$0';
        if (totalEl) totalEl.textContent = '$0';
        if (countBadge) countBadge.textContent = '0';
        return;
    }

    let subtotal = 0;
    let totalItems = 0;
    let html = '';

    cart.forEach(item => {
        const itemSubtotal = item.precio * item.cantidad;
        subtotal += itemSubtotal;
        totalItems += item.cantidad;

        html += `
            <div class="pos-cart-item">
                <div class="pos-cart-item-info">
                    <div class="pos-cart-item-name" title="${item.nombre}">${item.nombre}</div>
                    <div class="pos-cart-item-unit">${formatCLP(item.precio)} c/u &bull; <span class="badge ${item.destino === 'Cocina' ? 'badge-cocina' : item.destino === 'Bar' ? 'badge-bar' : 'badge-listo'}">${item.destino}</span></div>
                </div>

                <div class="pos-qty-control">
                    <button class="pos-qty-btn" onclick="updateQuantity(${item.id}, -1)">&minus;</button>
                    <span class="pos-qty-value">${item.cantidad}</span>
                    <button class="pos-qty-btn" onclick="updateQuantity(${item.id}, 1)">&plus;</button>
                </div>

                <div class="pos-cart-item-subtotal">
                    ${formatCLP(itemSubtotal)}
                </div>

                <button class="pos-cart-item-remove" onclick="removeFromCart(${item.id})" title="Eliminar">
                    <i class="bi bi-trash3-fill"></i>
                </button>
            </div>
        `;
    });

    container.innerHTML = html;
    if (subtotalEl) subtotalEl.textContent = formatCLP(subtotal);
    if (totalEl) totalEl.textContent = formatCLP(subtotal);
    if (countBadge) countBadge.textContent = totalItems;
}

function filterProductsByCategory(catId) {
    const cards = document.querySelectorAll('.pos-product-card');
    cards.forEach(card => {
        if (catId === 'todas' || card.dataset.cat === catId) {
            card.style.display = 'flex';
        } else {
            card.style.display = 'none';
        }
    });
}

function filterProductsByQuery(query) {
    const cards = document.querySelectorAll('.pos-product-card');
    cards.forEach(card => {
        const title = card.querySelector('.pos-product-title').textContent.toLowerCase();
        const desc = card.querySelector('.pos-product-desc')?.textContent.toLowerCase() || '';
        if (title.includes(query) || desc.includes(query)) {
            card.style.display = 'flex';
        } else {
            card.style.display = 'none';
        }
    });
}

/* ==========================================================================
   MODAL DE CONFIRMACIÓN DE VENTA
   ========================================================================== */
function openConfirmModal() {
    const modalEl = document.getElementById('modalConfirmarVenta');
    if (!modalEl || typeof bootstrap === 'undefined') return;

    const listEl = document.getElementById('confirmItemsList');
    const totalEl = document.getElementById('confirmTotal');
    const modEl = document.getElementById('confirmModalidad');
    const noteEl = document.getElementById('confirmNotes');
    const notesInput = document.getElementById('orderNotes');

    let total = 0;
    let itemsHtml = '';

    cart.forEach(item => {
        const itemSub = item.precio * item.cantidad;
        total += itemSub;
        itemsHtml += `
            <div class="d-flex justify-content-between align-items-center py-2 border-bottom border-secondary">
                <div>
                    <span class="fw-bold">${item.cantidad}x</span> ${item.nombre}
                    <div class="small text-muted">Destino: <strong>${item.destino}</strong></div>
                </div>
                <div class="fw-bold font-monospace text-info">${formatCLP(itemSub)}</div>
            </div>
        `;
    });

    if (listEl) listEl.innerHTML = itemsHtml;
    if (totalEl) totalEl.textContent = formatCLP(total);
    if (modEl) {
        modEl.textContent = modalidad === 'MESA' ? `Atención en ${mesaSeleccionada || 'Mesa no especificada'}` : 'Atención en BAR / Barra Rápida';
    }
    if (noteEl) {
        const noteText = notesInput?.value.trim() || 'Sin comentarios adicionales.';
        noteEl.textContent = noteText;
    }

    const modal = new bootstrap.Modal(modalEl);
    modal.show();
}

/* ==========================================================================
   MODAL DE TICKETS Y COMANDAS (Emisión visual)
   ========================================================================== */
function showTicketModal() {
    const ticketModalEl = document.getElementById('modalTicketEmision');
    if (!ticketModalEl || typeof bootstrap === 'undefined') return;

    // Calcular totales y generar comandas
    const folioNum = Math.floor(1000 + Math.random() * 9000);
    const dateStr = new Date().toLocaleDateString('es-CL');
    const timeStr = new Date().toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' });
    const notesText = document.getElementById('orderNotes')?.value.trim() || '';

    let total = 0;
    let ticketItemsHtml = '';
    let cocinaItemsHtml = '';
    let barItemsHtml = '';

    let hasCocina = false;
    let hasBar = false;

    cart.forEach(item => {
        const itemSub = item.precio * item.cantidad;
        total += itemSub;

        // Fila para el ticket de venta del cliente
        ticketItemsHtml += `
            <div class="thermal-row">
                <span>${item.cantidad}x ${item.nombre.substring(0, 20)}</span>
                <span>${formatCLP(itemSub)}</span>
            </div>
        `;

        // Si va a cocina
        if (item.destino === 'Cocina') {
            hasCocina = true;
            cocinaItemsHtml += `
                <div class="thermal-row fw-bold" style="font-size: 1rem;">
                    <span>[${item.cantidad}] ${item.nombre}</span>
                </div>
            `;
        }

        // Si va a bar
        if (item.destino === 'Bar') {
            hasBar = true;
            barItemsHtml += `
                <div class="thermal-row fw-bold" style="font-size: 1rem;">
                    <span>[${item.cantidad}] ${item.nombre}</span>
                </div>
            `;
        }
    });

    // Inyectar en Ticket Cliente
    const ticketFolioEl = document.getElementById('ticketFolio');
    const ticketDateTimeEl = document.getElementById('ticketDateTime');
    const ticketItemsContainer = document.getElementById('ticketItemsContainer');
    const ticketTotalEl = document.getElementById('ticketTotal');
    const ticketModEl = document.getElementById('ticketMod');

    if (ticketFolioEl) ticketFolioEl.textContent = `FOLIO: #${folioNum}`;
    if (ticketDateTimeEl) ticketDateTimeEl.textContent = `${dateStr} ${timeStr}`;
    if (ticketItemsContainer) ticketItemsContainer.innerHTML = ticketItemsHtml;
    if (ticketTotalEl) ticketTotalEl.textContent = formatCLP(total);
    if (ticketModEl) ticketModEl.textContent = modalidad === 'MESA' ? mesaSeleccionada : 'BAR / RETIRO';

    // Inyectar en Comanda Cocina
    const comandaCocinaWrapper = document.getElementById('comandaCocinaSlip');
    if (comandaCocinaWrapper) {
        if (hasCocina) {
            comandaCocinaWrapper.style.display = 'block';
            document.getElementById('cocinaFolio').textContent = `#${folioNum}`;
            document.getElementById('cocinaDestino').textContent = modalidad === 'MESA' ? mesaSeleccionada : 'BAR';
            document.getElementById('cocinaItems').innerHTML = cocinaItemsHtml;
            document.getElementById('cocinaNotas').textContent = notesText ? `NOTA: ${notesText}` : 'Sin notas';
        } else {
            comandaCocinaWrapper.style.display = 'none';
        }
    }

    // Inyectar en Comanda Bar
    const comandaBarWrapper = document.getElementById('comandaBarSlip');
    if (comandaBarWrapper) {
        if (hasBar) {
            comandaBarWrapper.style.display = 'block';
            document.getElementById('barFolio').textContent = `#${folioNum}`;
            document.getElementById('barDestino').textContent = modalidad === 'MESA' ? mesaSeleccionada : 'BAR';
            document.getElementById('barItems').innerHTML = barItemsHtml;
            document.getElementById('barNotas').textContent = notesText ? `NOTA: ${notesText}` : 'Sin notas';
        } else {
            comandaBarWrapper.style.display = 'none';
        }
    }

    // Vaciar carrito para la siguiente venta
    cart = [];
    if (document.getElementById('orderNotes')) document.getElementById('orderNotes').value = '';
    renderCart();

    const ticketModal = new bootstrap.Modal(ticketModalEl);
    ticketModal.show();
}

/* ==========================================================================
   3. COCINA KDS & BAR BDS (Simulación de Estados)
   ========================================================================== */
function initKdsInteractive() {
    const kdsButtons = document.querySelectorAll('.kds-action-btn');
    kdsButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const action = btn.dataset.action;
            const card = btn.closest('.pos-kds-card');
            const badge = card?.querySelector('.pos-kds-badge');

            if (action === 'preparar') {
                if (badge) {
                    badge.textContent = 'En preparación';
                    badge.className = 'badge bg-warning text-dark pos-kds-badge';
                }
                btn.textContent = 'Marcar como Preparado';
                btn.className = 'btn btn-success fw-bold w-100 kds-action-btn';
                btn.dataset.action = 'completar';
            } else if (action === 'completar') {
                if (badge) {
                    badge.textContent = 'Preparado';
                    badge.className = 'badge bg-success text-white pos-kds-badge';
                }
                btn.textContent = 'Entregado ✓';
                btn.className = 'btn btn-secondary disabled w-100';
                card.style.opacity = '0.6';
            }
        });
    });
}

/* ==========================================================================
   4. FILTROS EN TABLAS Y REPORTES
   ========================================================================== */
function initSearchFilters() {
    const genericSearch = document.getElementById('genericTableSearch');
    if (!genericSearch) return;

    genericSearch.addEventListener('input', (e) => {
        const q = e.target.value.toLowerCase().trim();
        const rows = document.querySelectorAll('.filterable-table tbody tr');
        rows.forEach(tr => {
            const text = tr.textContent.toLowerCase();
            tr.style.display = text.includes(q) ? '' : 'none';
        });
    });
}
