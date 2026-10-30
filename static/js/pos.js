/**
 * PARQUE SAFARI - SISTEMA WEB DE VENTAS POS (Fase 03 Transaccional)
 * Interactividad táctil, sincronización con PostgreSQL, cálculo CLP Neto/IVA y KDS/BDS en vivo
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Reloj en tiempo real en la barra superior
    initLiveClock();

    // 2. Control de Menús Desplegables / Acordeón en la Sidebar
    initSidebarAccordion();

    // 3. Botón de colapso de sidebar (Modo Pantalla Completa Tablet)
    initSidebarToggle();

    // 4. Sincronización de Rol e Identidad desde Servidor (AUD-006, AUD-010)
    initRoleManagement();

    // 5. Si estamos en la pantalla del POS, inicializar el motor de venta transaccional
    if (document.getElementById('posCartItems')) {
        initPosEngine();
    }

    // 6. Inicializar interactividad de Cocina KDS y Bar BDS conectada a PostgreSQL
    initKdsInteractive();

    // 7. Inicializar filtros de tablas y reportes
    initSearchFilters();
});

function getCsrfToken() {
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, 10) === 'csrftoken=') {
                return decodeURIComponent(cookie.substring(10));
            }
        }
    }
    const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return csrfInput ? csrfInput.value : '';
}

function generateIdempotencyKey() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
        return window.crypto.randomUUID();
    }
    return 'idem-' + Date.now() + '-' + Math.random().toString(36).substring(2, 12);
}

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
   2. CONTROL DE MENÚS DESPLEGABLES (ACORDEÓN SIDEBAR)
   ========================================================================== */
function initSidebarAccordion() {
    const headers = document.querySelectorAll('.pos-nav-accordion-header');
    headers.forEach(header => {
        header.addEventListener('click', () => {
            const groupKey = header.dataset.group;
            const collapseEl = document.getElementById(`group-${groupKey}`);
            if (!collapseEl) return;

            const isOpen = collapseEl.classList.contains('show');
            if (isOpen) {
                collapseEl.classList.remove('show');
                header.classList.remove('expanded');
            } else {
                collapseEl.classList.add('show');
                header.classList.add('expanded');
            }
        });

        const groupKey = header.dataset.group;
        const collapseEl = document.getElementById(`group-${groupKey}`);
        if (collapseEl && collapseEl.classList.contains('show')) {
            header.classList.add('expanded');
        }
    });
}

/* ==========================================================================
   3. BOTÓN COLAPSO DE SIDEBAR (MODO PANTALLA COMPLETA TABLET)
   ========================================================================== */
function initSidebarToggle() {
    const toggleBtn = document.getElementById('btnToggleSidebar');
    if (!toggleBtn) return;

    const isCollapsed = localStorage.getItem('safari_sidebar_collapsed') === 'true';
    if (isCollapsed) {
        document.body.classList.add('sidebar-collapsed');
    }

    toggleBtn.addEventListener('click', () => {
        document.body.classList.toggle('sidebar-collapsed');
        const nowCollapsed = document.body.classList.contains('sidebar-collapsed');
        localStorage.setItem('safari_sidebar_collapsed', nowCollapsed);
    });
}

/* ==========================================================================
   4. SINCRONIZACIÓN DE IDENTIDAD Y FOCO DE ROL DESDE SERVIDOR (AUD-006, AUD-010)
   ========================================================================== */
function initRoleManagement() {
    try {
        localStorage.removeItem('safari_active_role');
    } catch (e) {}

    const logoutForm = document.getElementById('logoutForm');
    if (logoutForm) {
        logoutForm.addEventListener('submit', () => {
            try {
                localStorage.removeItem('safari_active_role');
                sessionStorage.clear();
            } catch (e) {}
        });
    }

    const focusRole = document.body.dataset.focusRole || document.body.dataset.authenticatedRole || '';
    if (!focusRole) return;

    const sideBadge = document.getElementById('sidebarRoleFocusBadge');
    const badgeBg = sideBadge ? sideBadge.style.background : 'rgba(16, 185, 129, 0.2)';
    const badgeColor = sideBadge ? sideBadge.style.color : '#34d399';

    document.querySelectorAll('.pos-nav-link').forEach(link => {
        const linkFocus = link.dataset.focusRole;
        const tag = link.querySelector('.role-focus-tag');
        if (tag) {
            if (linkFocus === focusRole) {
                tag.classList.remove('d-none');
                tag.style.background = badgeBg;
                tag.style.color = badgeColor;
                tag.style.borderColor = badgeColor;
            } else {
                tag.classList.add('d-none');
            }
        }
    });
}

/* ==========================================================================
   5. MOTOR TRANSACCIONAL DE CARRITO POS
   ========================================================================== */
let cart = [];
let modalidad = 'BAR'; // 'BAR' o 'MESA'
let mesaSeleccionada = null;
let modoMesaActual = 'nueva'; // 'nueva' o 'agregar'
let currentCheckoutIdempotencyKey = null;
let isSubmittingSale = false;

function calcularDesgloseCLP(totalBruto) {
    const total = Math.max(0, Math.round(Number(totalBruto) || 0));
    const subtotalNeto = Math.round(total / 1.19);
    const iva = total - subtotalNeto;
    return { subtotalNeto, iva, total };
}

function initPosEngine() {
    const workspace = document.getElementById('posWorkspace');
    const preselectedMesa = workspace?.dataset.preselectedMesa || '';
    const preselectedModo = workspace?.dataset.modoMesa || 'nueva';

    // Escuchar clicks en tarjetas de productos y menús/combos
    const productCards = document.querySelectorAll('.pos-product-card');
    productCards.forEach(card => {
        card.addEventListener('click', () => {
            const itemType = card.dataset.itemType || 'producto';
            const id = parseInt(card.dataset.id, 10);
            const nombre = card.dataset.nombre;
            const precio = parseInt(card.dataset.precio, 10);
            const destino = card.dataset.destino || 'Directo';
            const tipo = card.dataset.tipo || 'Producto listo';
            const key = `${itemType}-${id}`;

            addToCart({ key, itemType, id, nombre, precio, destino, tipo });
        });
    });

    // Selector de Modalidad BAR vs MESA
    const btnBar = document.getElementById('btnModBar');
    const btnMesa = document.getElementById('btnModMesa');
    const mesaSelectorWrapper = document.getElementById('mesaSelectorWrapper');
    const modoMesaBadge = document.getElementById('modoMesaBadge');

    if (btnBar && btnMesa) {
        btnBar.addEventListener('click', () => {
            modalidad = 'BAR';
            mesaSeleccionada = null;
            modoMesaActual = 'nueva';
            btnBar.classList.add('active');
            btnMesa.classList.remove('active');
            if (mesaSelectorWrapper) mesaSelectorWrapper.style.display = 'none';
            if (modoMesaBadge) modoMesaBadge.classList.add('d-none');
        });

        btnMesa.addEventListener('click', () => {
            modalidad = 'MESA';
            btnMesa.classList.add('active');
            btnBar.classList.remove('active');
            if (mesaSelectorWrapper) mesaSelectorWrapper.style.display = 'flex';

            if (!mesaSeleccionada) {
                const mesaModalEl = document.getElementById('modalSeleccionMesa');
                if (mesaModalEl && typeof bootstrap !== 'undefined') {
                    const modal = new bootstrap.Modal(mesaModalEl);
                    modal.show();
                }
            }
        });
    }

    // Si se navegó desde Mapa de Mesas con ?mesa=...
    if (preselectedMesa && btnMesa) {
        modalidad = 'MESA';
        mesaSeleccionada = preselectedMesa;
        modoMesaActual = preselectedModo;
        btnMesa.classList.add('active');
        if (btnBar) btnBar.classList.remove('active');
        if (mesaSelectorWrapper) mesaSelectorWrapper.style.display = 'flex';
        const mesaLabel = document.getElementById('selectedMesaLabel');
        if (mesaLabel) mesaLabel.textContent = mesaSeleccionada;
        if (modoMesaBadge) {
            if (modoMesaActual === 'agregar') {
                modoMesaBadge.classList.remove('d-none');
            } else {
                modoMesaBadge.classList.add('d-none');
            }
        }
    }

    // Botones para elegir mesa en el modal (bloqueando mesas ocupadas)
    const mesaOptions = document.querySelectorAll('.mesa-option-btn');
    mesaOptions.forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.disabled || btn.dataset.estado !== 'Disponible') {
                return;
            }
            mesaSeleccionada = btn.dataset.mesaNum;
            modoMesaActual = 'nueva';
            const mesaLabel = document.getElementById('selectedMesaLabel');
            if (mesaLabel) mesaLabel.textContent = mesaSeleccionada;
            if (modoMesaBadge) modoMesaBadge.classList.add('d-none');

            const mesaModalEl = document.getElementById('modalSeleccionMesa');
            if (mesaModalEl && typeof bootstrap !== 'undefined') {
                const modal = bootstrap.Modal.getInstance(mesaModalEl);
                if (modal) modal.hide();
            }
        });
    });

    // Filtros de categoría en catálogo (incluyendo 'combos' -> Menús & Combos)
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
            currentCheckoutIdempotencyKey = null;
            renderCart();
        });
    }

    // Botón Cobrar / Abrir Confirmación de Venta
    const btnCheckout = document.getElementById('btnCheckout');
    if (btnCheckout) {
        btnCheckout.addEventListener('click', () => {
            if (cart.length === 0) {
                return;
            }

            if (modalidad === 'MESA' && !mesaSeleccionada) {
                const mesaModalEl = document.getElementById('modalSeleccionMesa');
                if (mesaModalEl && typeof bootstrap !== 'undefined') {
                    const modal = new bootstrap.Modal(mesaModalEl);
                    modal.show();
                }
                return;
            }

            currentCheckoutIdempotencyKey = generateIdempotencyKey();
            openConfirmModal();
        });
    }

    // Botón dentro del modal de confirmación: enviar transacción real al servidor
    const btnFinalizarVenta = document.getElementById('btnFinalizarVenta');
    if (btnFinalizarVenta) {
        btnFinalizarVenta.addEventListener('click', () => {
            submitSaleToServer();
        });
    }

    // Mostrar/ocultar selector de colaborador cuando se elige Vale Fiado
    const radiosPago = document.querySelectorAll('input[name="medioPago"]');
    const fiadoWrapper = document.getElementById('fiadoSelectorWrapper');
    radiosPago.forEach(radio => {
        radio.addEventListener('change', () => {
            if (fiadoWrapper) {
                if (radio.value === 'Vale Fiado' && radio.checked) {
                    fiadoWrapper.classList.remove('d-none');
                } else {
                    fiadoWrapper.classList.add('d-none');
                }
            }
        });
    });

    renderCart();
}

function addToCart(item) {
    const existing = cart.find(x => x.key === item.key);
    if (existing) {
        existing.cantidad += 1;
    } else {
        cart.push({ ...item, cantidad: 1 });
    }
    currentCheckoutIdempotencyKey = null;
    renderCart();
}

function updateQuantity(key, delta) {
    const item = cart.find(x => x.key === key);
    if (!item) return;

    item.cantidad += delta;
    if (item.cantidad <= 0) {
        cart = cart.filter(x => x.key !== key);
    }
    currentCheckoutIdempotencyKey = null;
    renderCart();
}

function removeFromCart(key) {
    cart = cart.filter(x => x.key !== key);
    currentCheckoutIdempotencyKey = null;
    renderCart();
}

function formatCLP(amount) {
    const val = Math.round(Number(amount) || 0);
    return '$' + val.toLocaleString('es-CL');
}

function getBadgeClassForDestino(destino) {
    if (!destino) return 'badge-listo';
    const d = destino.toLowerCase();
    if (d.includes('cocina')) return 'badge-cocina';
    if (d.includes('bar')) return 'badge-bar';
    return 'badge-listo';
}

function renderCart() {
    const container = document.getElementById('posCartItems');
    const subtotalEl = document.getElementById('cartSubtotal');
    const ivaEl = document.getElementById('cartIva');
    const totalEl = document.getElementById('cartTotal');
    const countBadge = document.getElementById('cartItemsCount');

    if (!container) return;

    if (cart.length === 0) {
        container.innerHTML = `
            <div class="pos-cart-empty">
                <i class="bi bi-cart-x"></i>
                <p class="mb-0 fw-semibold small">Carrito vacío</p>
                <small class="text-secondary" style="font-size: 0.72rem;">Toque productos o combos del catálogo para agregar</small>
            </div>
        `;
        if (subtotalEl) subtotalEl.textContent = '$0';
        if (ivaEl) ivaEl.textContent = '$0';
        if (totalEl) totalEl.textContent = '$0';
        if (countBadge) countBadge.textContent = '0';
        return;
    }

    let totalBruto = 0;
    let totalItems = 0;
    let html = '';

    cart.forEach(item => {
        const itemSubtotal = item.precio * item.cantidad;
        totalBruto += itemSubtotal;
        totalItems += item.cantidad;
        const badgeCls = getBadgeClassForDestino(item.destino);

        html += `
            <div class="pos-cart-item">
                <div class="pos-cart-item-info">
                    <div class="pos-cart-item-name" title="${item.nombre}">${item.nombre}</div>
                    <div class="pos-cart-item-unit">${formatCLP(item.precio)} c/u &bull; <span class="badge ${badgeCls}">${item.destino}</span></div>
                </div>

                <div class="pos-qty-control">
                    <button type="button" class="pos-qty-btn" onclick="updateQuantity('${item.key}', -1)">&minus;</button>
                    <span class="pos-qty-value">${item.cantidad}</span>
                    <button type="button" class="pos-qty-btn" onclick="updateQuantity('${item.key}', 1)">&plus;</button>
                </div>

                <div class="pos-cart-item-subtotal">
                    ${formatCLP(itemSubtotal)}
                </div>

                <button type="button" class="pos-cart-item-remove" onclick="removeFromCart('${item.key}')" title="Eliminar">
                    <i class="bi bi-trash3-fill"></i>
                </button>
            </div>
        `;
    });

    const desglose = calcularDesgloseCLP(totalBruto);

    container.innerHTML = html;
    if (subtotalEl) subtotalEl.textContent = formatCLP(desglose.subtotalNeto);
    if (ivaEl) ivaEl.textContent = formatCLP(desglose.iva);
    if (totalEl) totalEl.textContent = formatCLP(desglose.total);
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
        const title = card.querySelector('.pos-product-title')?.textContent.toLowerCase() || '';
        const desc = card.querySelector('.pos-product-desc')?.textContent.toLowerCase() || '';
        if (title.includes(query) || desc.includes(query)) {
            card.style.display = 'flex';
        } else {
            card.style.display = 'none';
        }
    });
}

/* ==========================================================================
   MODAL DE CONFIRMACIÓN Y ENVÍO TRANSACCIONAL AL SERVIDOR
   ========================================================================== */
function openConfirmModal() {
    const modalEl = document.getElementById('modalConfirmarVenta');
    if (!modalEl || typeof bootstrap === 'undefined') return;

    const errBox = document.getElementById('posCheckoutError');
    if (errBox) {
        errBox.classList.add('d-none');
        errBox.textContent = '';
    }

    const listEl = document.getElementById('confirmItemsList');
    const subEl = document.getElementById('confirmSubtotal');
    const ivaEl = document.getElementById('confirmIva');
    const totalEl = document.getElementById('confirmTotal');
    const modEl = document.getElementById('confirmModalidad');
    const noteEl = document.getElementById('confirmNotes');
    const notesInput = document.getElementById('orderNotes');

    let totalBruto = 0;
    let itemsHtml = '';

    cart.forEach(item => {
        const itemSub = item.precio * item.cantidad;
        totalBruto += itemSub;
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

    const desglose = calcularDesgloseCLP(totalBruto);

    if (listEl) listEl.innerHTML = itemsHtml;
    if (subEl) subEl.textContent = formatCLP(desglose.subtotalNeto);
    if (ivaEl) ivaEl.textContent = formatCLP(desglose.iva);
    if (totalEl) totalEl.textContent = formatCLP(desglose.total);
    if (modEl) {
        modEl.textContent = modalidad === 'MESA'
            ? `Atención en ${mesaSeleccionada || 'Mesa no especificada'} (Boleta Diferida)`
            : 'Atención en BAR / Barra Rápida (Boleta Inmediata)';
    }
    if (noteEl) {
        const noteText = notesInput?.value.trim() || 'Sin comentarios adicionales.';
        noteEl.textContent = noteText;
    }

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
}

async function submitSaleToServer() {
    if (isSubmittingSale || cart.length === 0) return;

    const workspace = document.getElementById('posWorkspace');
    const endpointUrl = workspace?.dataset.procesarUrl || '/pos/procesar-venta/';
    const btnFinalizar = document.getElementById('btnFinalizarVenta');
    const errBox = document.getElementById('posCheckoutError');
    const notesInput = document.getElementById('orderNotes');
    const checkedPago = document.querySelector('input[name="medioPago"]:checked');
    const metodoPago = checkedPago ? checkedPago.value : 'Efectivo';
    const fiadoSelect = document.getElementById('selectColaboradorFiado');
    const rutFiado = (metodoPago === 'Vale Fiado' && fiadoSelect) ? fiadoSelect.value.trim() : '';

    if (!currentCheckoutIdempotencyKey) {
        currentCheckoutIdempotencyKey = generateIdempotencyKey();
    }

    const payload = {
        idempotency_key: currentCheckoutIdempotencyKey,
        modalidad: modalidad,
        mesa_numero: modalidad === 'MESA' ? mesaSeleccionada : null,
        modo_mesa: modalidad === 'MESA' ? modoMesaActual : 'nueva',
        metodo_pago: metodoPago,
        rut_fiado: rutFiado || null,
        notas: notesInput ? notesInput.value.trim() : '',
        items: cart.map(item => ({
            tipo: item.itemType || 'producto',
            id: item.id,
            cantidad: item.cantidad,
        })),
    };

    isSubmittingSale = true;
    if (btnFinalizar) {
        btnFinalizar.disabled = true;
        btnFinalizar.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>PROCESANDO...';
    }
    if (errBox) {
        errBox.classList.add('d-none');
        errBox.textContent = '';
    }

    try {
        const response = await fetch(endpointUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify(payload),
        });

        const data = await response.json();

        if (!response.ok || !data.ok) {
            if (errBox) {
                errBox.textContent = data.error || 'No fue posible registrar la venta en el servidor.';
                errBox.classList.remove('d-none');
            }
            return;
        }

        // Cerrar modal de confirmación y mostrar comprobantes reales devueltos por PostgreSQL
        const modalConfEl = document.getElementById('modalConfirmarVenta');
        if (modalConfEl && typeof bootstrap !== 'undefined') {
            const modalConf = bootstrap.Modal.getInstance(modalConfEl);
            if (modalConf) modalConf.hide();
        }

        // Si se ocupó una mesa en la transacción, actualizar su botón en el modal selector
        if (data.venta && data.venta.mesa_numero) {
            const btnMesaOpt = document.querySelector(`.mesa-option-btn[data-mesa-num="${data.venta.mesa_numero}"]`);
            if (btnMesaOpt) {
                btnMesaOpt.disabled = true;
                btnMesaOpt.dataset.estado = 'Ocupada';
                btnMesaOpt.classList.remove('btn-outline-success');
                btnMesaOpt.classList.add('btn-outline-danger', 'opacity-50');
                const statusLabel = btnMesaOpt.querySelector('.mesa-option-status');
                if (statusLabel) {
                    statusLabel.textContent = 'Ocupada';
                    statusLabel.className = 'd-block text-danger fw-bold mesa-option-status';
                }
            }
        }

        // Limpiar estado del carrito tras confirmación del servidor
        cart = [];
        currentCheckoutIdempotencyKey = null;
        if (notesInput) notesInput.value = '';
        if (modalidad === 'MESA') {
            mesaSeleccionada = null;
            modoMesaActual = 'nueva';
            const mesaLabel = document.getElementById('selectedMesaLabel');
            if (mesaLabel) mesaLabel.textContent = 'Sin seleccionar';
            const modoMesaBadge = document.getElementById('modoMesaBadge');
            if (modoMesaBadge) modoMesaBadge.classList.add('d-none');
        }
        renderCart();

        showTicketModalFromServer(data.venta);
    } catch (networkErr) {
        if (errBox) {
            errBox.textContent = 'Error de comunicación con el servidor. Verifique su conexión e intente nuevamente.';
            errBox.classList.remove('d-none');
        }
    } finally {
        isSubmittingSale = false;
        if (btnFinalizar) {
            btnFinalizar.disabled = false;
            btnFinalizar.innerHTML = '<i class="bi bi-check2-all fs-5"></i><span>CONFIRMAR VENTA</span>';
        }
    }
}

/* ==========================================================================
   MODAL DE TICKETS Y COMANDAS (Renderizado desde datos reales del servidor)
   ========================================================================== */
function showTicketModalFromServer(venta) {
    const ticketModalEl = document.getElementById('modalTicketEmision');
    if (!ticketModalEl || typeof bootstrap === 'undefined' || !venta) return;

    const ticketFolioEl = document.getElementById('ticketFolio');
    const ticketDateTimeEl = document.getElementById('ticketDateTime');
    const ticketCajeroEl = document.getElementById('ticketCajero');
    const ticketModEl = document.getElementById('ticketMod');
    const ticketItemsContainer = document.getElementById('ticketItemsContainer');
    const ticketSubtotalEl = document.getElementById('ticketSubtotal');
    const ticketIvaEl = document.getElementById('ticketIva');
    const ticketTotalEl = document.getElementById('ticketTotal');
    const ticketMetodoPagoEl = document.getElementById('ticketMetodoPago');
    const ticketBarcodeTextEl = document.getElementById('ticketBarcodeText');
    const btnVerTicketCompleto = document.getElementById('btnVerTicketCompleto');

    if (ticketFolioEl) ticketFolioEl.textContent = `FOLIO: #${venta.venta_num}`;
    if (ticketDateTimeEl) ticketDateTimeEl.textContent = `${venta.fecha} ${venta.hora_completa || venta.hora}`;
    if (ticketCajeroEl) ticketCajeroEl.textContent = venta.cajero;
    if (ticketModEl) {
        ticketModEl.textContent = venta.modalidad === 'MESA'
            ? `${venta.ubicacion} (Boleta Diferida al Pago)`
            : `${venta.ubicacion} (Boleta Inmediata)`;
    }

    if (ticketItemsContainer && Array.isArray(venta.items)) {
        ticketItemsContainer.innerHTML = venta.items.map(it => `
            <div class="thermal-row">
                <span>${it.cant}x ${String(it.nombre).substring(0, 22)}</span>
                <span>${it.subtotal_fmt}</span>
            </div>
        `).join('');
    }

    if (ticketSubtotalEl) ticketSubtotalEl.textContent = venta.subtotal_fmt;
    if (ticketIvaEl) ticketIvaEl.textContent = venta.iva_fmt;
    if (ticketTotalEl) ticketTotalEl.textContent = venta.total_fmt;
    if (ticketMetodoPagoEl) ticketMetodoPagoEl.textContent = String(venta.metodo_pago || 'Efectivo').toUpperCase();
    if (ticketBarcodeTextEl) ticketBarcodeTextEl.textContent = `SAF-2026-${venta.venta_num}`;
    if (btnVerTicketCompleto && venta.ticket_url) {
        btnVerTicketCompleto.href = venta.ticket_url;
    }

    const slipTypeEl = document.querySelector('#modalTicketEmision .thermal-slip-type');
    if (slipTypeEl) {
        slipTypeEl.textContent = venta.tipo_documento || 'BOLETA ELECTRÓNICA DE VENTA';
        if (venta.modalidad === 'MESA' && !venta.boleta_emitida) {
            slipTypeEl.style.background = '#0284c7';
            slipTypeEl.style.color = '#fff';
        } else {
            slipTypeEl.style.background = '#1e293b';
            slipTypeEl.style.color = '#fff';
        }
    }

    // Comanda de Cocina
    const comandaCocinaWrapper = document.getElementById('comandaCocinaSlip');
    if (comandaCocinaWrapper) {
        if (venta.comanda_cocina) {
            const cc = venta.comanda_cocina;
            comandaCocinaWrapper.style.display = 'block';
            const elFolio = document.getElementById('cocinaFolio');
            const elDest = document.getElementById('cocinaDestino');
            const elHora = document.getElementById('cocinaHora');
            const elGarzon = document.getElementById('cocinaGarzon');
            const elItems = document.getElementById('cocinaItems');
            const elNotas = document.getElementById('cocinaNotas');

            if (elFolio) elFolio.textContent = cc.codigo;
            if (elDest) elDest.textContent = cc.ubicacion;
            if (elHora) elHora.textContent = cc.hora;
            if (elGarzon) elGarzon.textContent = cc.garzon;
            if (elItems && Array.isArray(cc.items)) {
                elItems.innerHTML = cc.items.map(item => `
                    <div class="thermal-row fw-bold" style="font-size: 0.95rem;">
                        <span>[${item.cant}] ${item.nombre}</span>
                    </div>
                `).join('');
            }
            if (elNotas) elNotas.textContent = cc.notas ? `NOTA: ${cc.notas}` : 'Sin notas';
        } else {
            comandaCocinaWrapper.style.display = 'none';
        }
    }

    // Comanda de Bar
    const comandaBarWrapper = document.getElementById('comandaBarSlip');
    if (comandaBarWrapper) {
        if (venta.comanda_bar) {
            const cb = venta.comanda_bar;
            comandaBarWrapper.style.display = 'block';
            const elFolio = document.getElementById('barFolio');
            const elDest = document.getElementById('barDestino');
            const elHora = document.getElementById('barHora');
            const elGarzon = document.getElementById('barGarzon');
            const elItems = document.getElementById('barItems');
            const elNotas = document.getElementById('barNotas');

            if (elFolio) elFolio.textContent = cb.codigo;
            if (elDest) elDest.textContent = cb.ubicacion;
            if (elHora) elHora.textContent = cb.hora;
            if (elGarzon) elGarzon.textContent = cb.garzon;
            if (elItems && Array.isArray(cb.items)) {
                elItems.innerHTML = cb.items.map(item => `
                    <div class="thermal-row fw-bold" style="font-size: 0.95rem;">
                        <span>[${item.cant}] ${item.nombre}</span>
                    </div>
                `).join('');
            }
            if (elNotas) elNotas.textContent = cb.notas ? `NOTA: ${cb.notas}` : 'Sin notas';
        } else {
            comandaBarWrapper.style.display = 'none';
        }
    }

    const ticketModal = bootstrap.Modal.getOrCreateInstance(ticketModalEl);
    ticketModal.show();
}

/* ==========================================================================
   6. COCINA KDS & BAR BDS (Actualización Transaccional en PostgreSQL)
   ========================================================================== */
function initKdsInteractive() {
    const kdsButtons = document.querySelectorAll('.kds-action-btn');
    kdsButtons.forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (btn.disabled) return;

            const card = btn.closest('.pos-kds-card');
            const grid = btn.closest('[data-comanda-url]');
            const endpointUrl = grid?.dataset.comandaUrl || '/comandas/estado/';
            const codigoComanda = btn.dataset.codigo || card?.dataset.pedidoId;
            const area = (btn.dataset.area || (grid?.id === 'bdsGrid' ? 'BAR' : 'COCINA')).toUpperCase();
            const action = btn.dataset.action;

            if (!codigoComanda || !action) return;

            btn.disabled = true;
            try {
                const response = await fetch(endpointUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': getCsrfToken(),
                    },
                    body: JSON.stringify({
                        codigo_comanda: codigoComanda,
                        accion: action,
                    }),
                });
                const data = await response.json();
                if (!response.ok || !data.ok) {
                    btn.disabled = false;
                    return;
                }

                const nuevoEstado = data.estado_actual;
                const badge = card?.querySelector('.pos-kds-badge');
                if (card) {
                    card.dataset.estado = nuevoEstado;
                    if (data.urgencia) {
                        card.dataset.urgencia = data.urgencia;
                    }
                }

                if (nuevoEstado === 'En preparación') {
                    if (badge) {
                        badge.textContent = 'En preparación';
                        badge.className = 'badge bg-warning text-dark pos-kds-badge';
                    }
                    btn.dataset.action = 'completar';
                    btn.className = 'btn btn-success fw-bold w-100 kds-action-btn';
                    btn.innerHTML = area === 'BAR'
                        ? '<i class="bi bi-check2-circle me-1"></i> Listo para Retiro'
                        : '<i class="bi bi-check2-circle me-1"></i> Marcar como Preparado';
                    btn.disabled = false;
                } else if (nuevoEstado === 'Preparado' || nuevoEstado === 'Listo') {
                    if (badge) {
                        badge.textContent = nuevoEstado;
                        badge.className = 'badge bg-success text-white pos-kds-badge';
                    }
                    if (card) {
                        card.classList.remove('urgente', 'advertencia');
                    }
                    btn.dataset.action = 'entregar';
                    btn.className = area === 'BAR'
                        ? 'btn btn-outline-info fw-bold w-100 kds-action-btn'
                        : 'btn btn-outline-success fw-bold w-100 kds-action-btn';
                    btn.innerHTML = area === 'BAR'
                        ? '<i class="bi bi-check-all me-1"></i> Entregado en Barra'
                        : '<i class="bi bi-check-all me-1"></i> Despachar / Entregado';
                    btn.disabled = false;
                } else if (nuevoEstado === 'Entregado') {
                    if (badge) {
                        badge.textContent = 'Entregado';
                        badge.className = 'badge bg-secondary text-white pos-kds-badge';
                    }
                    if (card) {
                        card.style.display = 'none';
                    }
                }

                // Sincronizar contadores y filtros con la respuesta oficial del servidor
                if (area === 'BAR' && typeof window.refreshBdsBoardState === 'function') {
                    window.refreshBdsBoardState(data.contadores);
                } else if (typeof window.refreshKdsBoardState === 'function') {
                    window.refreshKdsBoardState(data.contadores);
                }
            } catch (err) {
                btn.disabled = false;
            }
        });
    });
}

/* ==========================================================================
   7. FILTROS EN TABLAS Y REPORTES
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
