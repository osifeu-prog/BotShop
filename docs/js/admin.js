
// Admin Panel logic – טעינת תשלומים ומדדים מה-API המאובטח

document.addEventListener('DOMContentLoaded', () => {
    const statusFilter = document.getElementById('payment-status-filter');
    const refreshBtn = document.getElementById('refresh-payments');
    const paymentsBody = document.querySelector('#payments-table tbody');
    const metricsBox = document.getElementById('admin-metrics');
    const pendingList = document.getElementById('pending-payments-list');
    const approvedUsersList = document.getElementById('approved-users-list');

    const API_BASE = window.BOTSHOP_API_BASE || 'https://botshop-production.up.railway.app';

    let adminToken = window.BOTSHOP_ADMIN_TOKEN || null;

    function ensureToken() {
        if (!adminToken) {
            adminToken = window.prompt('הכנס ADMIN_DASH_TOKEN לצפייה במידע ניהולי:');
            window.BOTSHOP_ADMIN_TOKEN = adminToken;
        }
    }

    async function fetchJson(path, params) {
        ensureToken();
        const url = new URL(API_BASE + path);
        if (params) {
            Object.entries(params).forEach(([k, v]) => {
                if (v !== null && v !== undefined && v !== '') {
                    url.searchParams.set(k, v);
                }
            });
        }
        const res = await fetch(url.toString(), {
            headers: {
                'X-Admin-Token': adminToken
            }
        });
        if (!res.ok) {
            console.warn('Admin API error', res.status);
            throw new Error('Admin API error ' + res.status);
        }
        return await res.json();
    }

    async function loadFinanceSummary() {
        try {
            const data = await fetchJson('/api/admin/finance-summary');
            if (!metricsBox) return;

            const reserve = data.reserve || {};
            const approvals = data.approvals || {};
            const investors = data.investors || {};

            metricsBox.innerHTML = `
                <div><strong>סה\"כ תשלומים:</strong> ${reserve.total_payments || 0}</div>
                <div><strong>סה\"כ סכום:</strong> ${(reserve.total_amount || 0).toFixed(2)} ₪</div>
                <div><strong>סה\"כ רזרבה (49%):</strong> ${(reserve.total_reserve || 0).toFixed(2)} ₪</div>
                <div><strong>סה\"כ נטו:</strong> ${(reserve.total_net || 0).toFixed(2)} ₪</div>
                <hr>
                <div><strong>Pending:</strong> ${approvals.pending || 0}</div>
                <div><strong>Approved:</strong> ${approvals.approved || 0}</div>
                <div><strong>Rejected:</strong> ${approvals.rejected || 0}</div>
                <hr>
                <div><strong>משקיעים מאושרים:</strong> ${investors.approved_investors || 0}</div>
                <div><strong>סה\"כ משקיעים:</strong> ${investors.total_investors || 0}</div>
                <div><strong>סכום כולל (₪):</strong> ${(investors.total_amount || 0).toFixed(2)} ₪</div>
                <div><strong>כרטיס ממוצע (₪):</strong> ${(investors.avg_ticket || 0).toFixed(2)} ₪</div>
            `;
        } catch (err) {
            console.error('Failed loading finance summary', err);
        }
    }

    function renderPayments(payments) {
        if (paymentsBody) {
            paymentsBody.innerHTML = '';
        }
        if (pendingList) {
            pendingList.innerHTML = '';
        }
        if (approvedUsersList) {
            approvedUsersList.innerHTML = '';
        }

        if (!payments || !payments.length) {
            if (paymentsBody) {
                const tr = document.createElement('tr');
                const td = document.createElement('td');
                td.colSpan = 7;
                td.textContent = 'אין נתונים להצגה כרגע.';
                tr.appendChild(td);
                paymentsBody.appendChild(tr);
            }
            return;
        }

        const approvedUsers = new Map();

        payments.forEach(p => {
            // טבלת תשלומים
            if (paymentsBody) {
                const tr = document.createElement('tr');

                const createdAt = p.created_at ? new Date(p.created_at) : null;
                const createdText = createdAt ? createdAt.toLocaleString('he-IL') : '';

                const cols = [
                    p.id,
                    p.user_id,
                    p.username || '',
                    p.pay_method || '',
                    p.status || '',
                    (p.amount || 0).toFixed(2) + ' ₪',
                    (p.reserve_amount || 0).toFixed(2) + ' ₪',
                    (p.net_amount || 0).toFixed(2) + ' ₪',
                    createdText
                ];

                cols.forEach(val => {
                    const td = document.createElement('td');
                    td.textContent = val;
                    tr.appendChild(td);
                });

                paymentsBody.appendChild(tr);
            }

            // רשימת pending
            if (pendingList && p.status === 'pending') {
                const div = document.createElement('div');
                div.className = 'pending-item';
                div.textContent = `ID ${p.id} – user_id=${p.user_id} (${p.username || 'ללא שם'}) – ${p.amount || 0} ₪`;
                pendingList.appendChild(div);
            }

            // משתמשים מאושרים
            if (approvedUsersList && p.status === 'approved') {
                const key = p.user_id;
                if (!approvedUsers.has(key)) {
                    approvedUsers.set(key, p);
                }
            }
        });

        if (approvedUsersList && approvedUsers.size > 0) {
            approvedUsers.forEach(p => {
                const div = document.createElement('div');
                div.className = 'approved-user';
                div.textContent = `user_id=${p.user_id} (${p.username || 'ללא שם'}) – תשלום מאושר`;
                approvedUsersList.appendChild(div);
            });
        }
    }

    async function loadPayments() {
        try {
            const status = statusFilter ? statusFilter.value : null;
            const data = await fetchJson('/api/admin/payments', {
                limit: 200,
                status: status && status !== 'all' ? status : null
            });
            renderPayments(data.items || []);
        } catch (err) {
            console.error('Failed loading payments', err);
        }
    }

    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            loadFinanceSummary();
            loadPayments();
        });
    }

    // טעינה ראשונית
    loadFinanceSummary();
    loadPayments();
});
