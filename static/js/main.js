// CampusLink Main JavaScript File

// Wait for DOM to load
document.addEventListener('DOMContentLoaded', function() {
    
    // Auto-dismiss alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            alert.classList.add('fade-out');
            setTimeout(function() {
                alert.remove();
            }, 500);
        }, 5000);
    });
    
    // Form validation
    const forms = document.querySelectorAll('form');
    forms.forEach(function(form) {
        form.addEventListener('submit', function(e) {
            const requiredFields = form.querySelectorAll('[required]');
            let isValid = true;
            
            requiredFields.forEach(function(field) {
                if (!field.value.trim()) {
                    isValid = false;
                    field.classList.add('is-invalid');
                    
                    // Add error message if not exists
                    let errorDiv = field.nextElementSibling;
                    if (!errorDiv || !errorDiv.classList.contains('invalid-feedback')) {
                        errorDiv = document.createElement('div');
                        errorDiv.className = 'invalid-feedback';
                        errorDiv.textContent = 'This field is required.';
                        field.parentNode.insertBefore(errorDiv, field.nextSibling);
                    }
                } else {
                    field.classList.remove('is-invalid');
                    const errorDiv = field.nextElementSibling;
                    if (errorDiv && errorDiv.classList.contains('invalid-feedback')) {
                        errorDiv.remove();
                    }
                }
            });
            
            if (!isValid) {
                e.preventDefault();
                // Scroll to first error
                const firstError = document.querySelector('.is-invalid');
                if (firstError) {
                    firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            }
        });
    });
    
    // Add fade-out class for alerts
    const style = document.createElement('style');
    style.textContent = `
        .fade-out {
            opacity: 0;
            transition: opacity 0.5s ease-out;
        }
        .is-invalid {
            border-color: #dc3545 !important;
        }
        .invalid-feedback {
            display: block;
            color: #dc3545;
            font-size: 0.875rem;
            margin-top: 0.25rem;
        }
    `;
    document.head.appendChild(style);
    
    // Confirm before cancel registration
    const cancelButtons = document.querySelectorAll('.cancel-registration');
    cancelButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            if (!confirm('Are you sure you want to cancel your registration?')) {
                e.preventDefault();
            }
        });
    });
    
    // Confirm before deleting event
    const deleteButtons = document.querySelectorAll('.delete-event');
    deleteButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            if (!confirm('Are you sure you want to delete this event? This action cannot be undone.')) {
                e.preventDefault();
            }
        });
    });
    
    // Date picker enhancements
    const dateInputs = document.querySelectorAll('input[type="date"]');
    dateInputs.forEach(function(input) {
        // Set min date to today for start date
        if (input.id === 'start_date' || input.name === 'start_date') {
            const today = new Date().toISOString().split('T')[0];
            input.setAttribute('min', today);
        }
        
        // Add change event for end date
        input.addEventListener('change', function() {
            const startDate = document.querySelector('#start_date, [name="start_date"]');
            const endDate = document.querySelector('#end_date, [name="end_date"]');
            
            if (startDate && endDate && endDate.value) {
                if (endDate.value < startDate.value) {
                    alert('End date cannot be before start date!');
                    endDate.value = '';
                }
            }
        });
    });
    
    // Live search for events
    const searchInput = document.getElementById('search-events');
    if (searchInput) {
        searchInput.addEventListener('keyup', function() {
            const searchTerm = this.value.toLowerCase();
            const eventCards = document.querySelectorAll('.event-card');
            
            eventCards.forEach(function(card) {
                const title = card.querySelector('.card-title').textContent.toLowerCase();
                const description = card.querySelector('.card-text')?.textContent.toLowerCase() || '';
                
                if (title.includes(searchTerm) || description.includes(searchTerm)) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        });
    }
    
    // Filter events by type
    const filterButtons = document.querySelectorAll('.filter-btn');
    filterButtons.forEach(function(button) {
        button.addEventListener('click', function() {
            const filter = this.dataset.filter;
            const eventCards = document.querySelectorAll('.event-card');
            
            filterButtons.forEach(btn => btn.classList.remove('active'));
            this.classList.add('active');
            
            eventCards.forEach(function(card) {
                if (filter === 'all' || card.dataset.type === filter) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        });
    });
    
    // Attendance toggle
    const attendanceToggles = document.querySelectorAll('.attendance-toggle');
    attendanceToggles.forEach(function(toggle) {
        toggle.addEventListener('change', function() {
            const studentId = this.dataset.studentId;
            const eventId = this.dataset.eventId;
            const isPresent = this.checked;
            
            // Send AJAX request to update attendance
            fetch('/update-attendance', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    event_id: eventId,
                    student_id: studentId,
                    attended: isPresent
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showToast('Attendance updated successfully!', 'success');
                } else {
                    showToast('Error updating attendance', 'error');
                    this.checked = !isPresent;
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showToast('Error updating attendance', 'error');
                this.checked = !isPresent;
            });
        });
    });
    
    // Toast notification function
    function showToast(message, type) {
        const toast = document.createElement('div');
        toast.className = `toast-notification toast-${type}`;
        toast.innerHTML = `
            <div class="toast-content">
                <i class="fas ${type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'}"></i>
                <span>${message}</span>
            </div>
        `;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.classList.add('show');
        }, 100);
        
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 3000);
    }
    
    // Add toast styles
    const toastStyle = document.createElement('style');
    toastStyle.textContent = `
        .toast-notification {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: white;
            border-radius: 8px;
            padding: 12px 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            transform: translateX(400px);
            transition: transform 0.3s ease-out;
            z-index: 1000;
        }
        .toast-notification.show {
            transform: translateX(0);
        }
        .toast-success {
            border-left: 4px solid #28a745;
        }
        .toast-error {
            border-left: 4px solid #dc3545;
        }
        .toast-content {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .toast-success i {
            color: #28a745;
        }
        .toast-error i {
            color: #dc3545;
        }
    `;
    document.head.appendChild(toastStyle);
    
    // Smooth scroll to top button
    const scrollTopBtn = document.createElement('button');
    scrollTopBtn.innerHTML = '<i class="fas fa-arrow-up"></i>';
    scrollTopBtn.className = 'scroll-top-btn';
    scrollTopBtn.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        width: 40px;
        height: 40px;
        border-radius: 50%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        cursor: pointer;
        display: none;
        z-index: 999;
        transition: all 0.3s;
    `;
    
    document.body.appendChild(scrollTopBtn);
    
    window.addEventListener('scroll', function() {
        if (window.pageYOffset > 300) {
            scrollTopBtn.style.display = 'block';
        } else {
            scrollTopBtn.style.display = 'none';
        }
    });
    
    scrollTopBtn.addEventListener('click', function() {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });
    
    // Add loading state to buttons
    const buttons = document.querySelectorAll('.btn');
    buttons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            if (this.type === 'submit') {
                const originalText = this.innerHTML;
                this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
                this.disabled = true;
                
                setTimeout(() => {
                    this.innerHTML = originalText;
                    this.disabled = false;
                }, 3000);
            }
        });
    });
});

// Console welcome message
console.log('%cCampusLink Smart Event Manager', 'color: #667eea; font-size: 16px; font-weight: bold;');
console.log('%cReal-time campus event management system', 'color: #764ba2; font-size: 12px;');