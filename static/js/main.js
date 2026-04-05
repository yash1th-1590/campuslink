document.addEventListener('DOMContentLoaded', function () {

    // ── Auto-dismiss alerts ──
    document.querySelectorAll('.alert').forEach(function (alert) {
        setTimeout(function () {
            alert.style.transition = 'opacity 0.5s';
            alert.style.opacity = '0';
            setTimeout(function () { alert.remove(); }, 500);
        }, 5000);
    });

    // ── Form validation ──
    document.querySelectorAll('form').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            const requiredFields = form.querySelectorAll('[required]');
            let isValid = true;
            requiredFields.forEach(function (field) {
                if (!field.value.trim()) {
                    isValid = false;
                    field.classList.add('is-invalid');
                    field.style.borderColor = 'var(--danger)';
                } else {
                    field.classList.remove('is-invalid');
                    field.style.borderColor = '';
                }
            });
            if (!isValid) {
                e.preventDefault();
                const firstError = document.querySelector('.is-invalid');
                if (firstError) firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        });
    });

    // ── Date inputs: set min to today ──
    document.querySelectorAll('input[type="date"]').forEach(function (input) {
        if (input.id === 'start_date' || input.name === 'start_date') {
            input.setAttribute('min', new Date().toISOString().split('T')[0]);
        }
        input.addEventListener('change', function () {
            const startDate = document.querySelector('#start_date, [name="start_date"]');
            const endDate = document.querySelector('#end_date, [name="end_date"]');
            if (startDate && endDate && endDate.value && endDate.value < startDate.value) {
                alert('End date cannot be before start date!');
                endDate.value = '';
            }
        });
    });

    // ── Toast notification system ──
    window.showToast = function (message, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `cl-toast cl-toast-${type}`;
        toast.innerHTML = `
            <div style="display:flex;align-items:center;gap:10px;">
                <i class="fas ${type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'}"
                   style="color:${type === 'success' ? 'var(--success)' : 'var(--danger)'};font-size:1rem;"></i>
                <span style="font-size:0.875rem;font-weight:500;">${message}</span>
            </div>`;
        document.body.appendChild(toast);
        setTimeout(() => toast.classList.add('show'), 100);
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    };

    // ── Confirm delete buttons ──
    document.querySelectorAll('[data-confirm]').forEach(function (el) {
        el.addEventListener('click', function (e) {
            if (!confirm(this.dataset.confirm)) e.preventDefault();
        });
    });

    // ── Submit button loading state ──
    document.querySelectorAll('form').forEach(function (form) {
        form.addEventListener('submit', function () {
            const submitBtn = form.querySelector('[type="submit"]');
            if (submitBtn && !form.querySelector('.is-invalid')) {
                const orig = submitBtn.innerHTML;
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Please wait...';
                submitBtn.disabled = true;
                setTimeout(() => {
                    submitBtn.innerHTML = orig;
                    submitBtn.disabled = false;
                }, 8000);
            }
        });
    });

    // ── Drag and drop for file upload ──
    document.querySelectorAll('.drop-zone').forEach(function (zone) {
        const input = zone.querySelector('input[type="file"]');

        zone.addEventListener('click', () => input && input.click());
        zone.addEventListener('dragover', (e) => {
            e.preventDefault();
            zone.classList.add('dragover');
        });
        zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
        zone.addEventListener('drop', (e) => {
            e.preventDefault();
            zone.classList.remove('dragover');
            if (input && e.dataTransfer.files.length) {
                input.files = e.dataTransfer.files;
                updateDropZone(zone, e.dataTransfer.files[0]);
            }
        });
        if (input) {
            input.addEventListener('change', function () {
                if (this.files.length) updateDropZone(zone, this.files[0]);
            });
        }
    });

    function updateDropZone(zone, file) {
        const label = zone.querySelector('.drop-zone-label');
        if (label) {
            label.innerHTML = `<i class="fas fa-file-check me-2" style="color:var(--success);"></i>
                <strong>${file.name}</strong>
                <div style="font-size:0.72rem;color:var(--text-muted);margin-top:4px;">${(file.size / 1024).toFixed(1)} KB</div>`;
        }
        zone.style.borderColor = 'var(--success)';
        zone.style.background = 'rgba(16,185,129,0.05)';
    }

    // ── Topbar search (client-side event filter if on events page) ──
    const searchInput = document.querySelector('.topbar-search input');
    if (searchInput) {
        searchInput.addEventListener('input', function () {
            const term = this.value.toLowerCase();
            document.querySelectorAll('.event-search-item').forEach(function (item) {
                const title = item.dataset.title || '';
                item.closest('.col-md-6, .col-xl-4') &&
                    (item.closest('.col-md-6, .col-xl-4').style.display =
                        title.toLowerCase().includes(term) ? '' : 'none');
            });
        });
    }

    console.log('%cCampusLink', 'color:#5b4cdb;font-size:18px;font-weight:800;');
    console.log('%cSmart Real-Time Event Manager', 'color:#f43f7f;font-size:12px;');
});