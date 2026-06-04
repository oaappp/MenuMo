// MenuMo - Main JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (el) {
        return new bootstrap.Tooltip(el);
    });

    // Toggle meal instructions
    document.querySelectorAll('.toggle-instructions').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            var instructions = this.closest('.meal-card').querySelector('.meal-instructions');
            if (instructions) {
                instructions.classList.toggle('show');
                this.textContent = instructions.classList.contains('show') ? '▲ Itago' : '▼ Instructions';
            }
        });
    });

    // Regenerate meal
    document.querySelectorAll('.regenerate-btn').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            var planId = this.dataset.planId;
            var day = this.dataset.day;
            var mealType = this.dataset.mealType;

            if (!planId || !day || !mealType) return;

            var mealCard = this.closest('.meal-card');
            var originalText = this.innerHTML;
            this.disabled = true;
            this.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

            fetch('/plan/' + planId + '/regenerate/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify({
                    day: day,
                    meal_type: mealType
                })
            })
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (data.success) {
                    // Update meal name
                    mealCard.querySelector('.meal-name').textContent = data.meal.name;

                    // Update cost
                    var costEl = mealCard.querySelector('.meal-cost');
                    if (costEl) costEl.textContent = '₱' + data.meal.estimated_cost;

                    // Update cook time
                    var cookTimeEl = mealCard.querySelector('.meal-cook-time');
                    if (cookTimeEl) cookTimeEl.textContent = data.meal.cook_time;

                    // Update instructions
                    var instructionsEl = mealCard.querySelector('.meal-instructions');
                    if (instructionsEl) {
                        instructionsEl.innerHTML = data.meal.instructions.replace(/\n/g, '<br>');
                        instructionsEl.classList.remove('show');
                    }

                    // Update day total
                    var dayCard = mealCard.closest('.day-card');
                    if (dayCard) {
                        var dayTotalEl = dayCard.querySelector('.day-total');
                        if (dayTotalEl) dayTotalEl.textContent = 'Day Total: ₱' + data.day_total;
                    }

                    // Update weekly total
                    var weeklyTotalEl = document.querySelector('.weekly-total-amount');
                    if (weeklyTotalEl) weeklyTotalEl.textContent = '₱' + data.weekly_total;

                    // Show success feedback
                    showToast('Meal updated!', 'success');
                } else {
                    showToast('Failed to regenerate meal', 'danger');
                }
            })
            .catch(function() {
                showToast('Connection error. Please try again.', 'danger');
            })
            .finally(function() {
                btn.innerHTML = originalText;
                btn.disabled = false;
            });
        });
    });

    // Save plan
    var saveBtn = document.getElementById('save-plan-btn');
    if (saveBtn) {
        saveBtn.addEventListener('click', function(e) {
            e.preventDefault();
            var planId = this.dataset.planId;

            fetch('/plan/' + planId + '/save/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCSRFToken()
                }
            })
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (data.success) {
                    showToast('Plan saved successfully!', 'success');
                    this.textContent = '✓ Saved';
                    this.disabled = true;
                }
            }.bind(this))
            .catch(function() {
                showToast('Failed to save plan', 'danger');
            });
        });
    }

    // Delete saved plan
    document.querySelectorAll('.delete-plan-btn').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            if (!confirm('Are you sure you want to delete this saved plan?')) return;

            var planId = this.dataset.planId;
            var card = this.closest('.saved-plan-card');

            fetch('/saved/' + planId + '/delete/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCSRFToken()
                }
            })
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (data.success) {
                    card.remove();
                    showToast('Plan deleted', 'success');
                }
            })
            .catch(function() {
                showToast('Failed to delete plan', 'danger');
            });
        });
    });

    // Grocery list checkboxes
    document.querySelectorAll('.grocery-checkbox').forEach(function(cb) {
        cb.addEventListener('change', function() {
            var item = this.closest('.grocery-item');
            if (this.checked) {
                item.classList.add('checked');
            } else {
                item.classList.remove('checked');
            }
        });
    });

    // Loading overlay
    var plannerForm = document.getElementById('planner-form');
    if (plannerForm) {
        plannerForm.addEventListener('submit', function() {
            document.getElementById('loading-overlay').classList.add('active');
        });
    }

    // Budget range display
    var budgetInput = document.getElementById('budget');
    var budgetDisplay = document.getElementById('budget-display');
    if (budgetInput && budgetDisplay) {
        budgetInput.addEventListener('input', function() {
            budgetDisplay.textContent = '₱' + parseInt(this.value).toLocaleString();
        });
    }
});

// Helper: Get CSRF token
function getCSRFToken() {
    var name = 'csrftoken';
    var cookies = document.cookie.split(';');
    for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i].trim();
        if (cookie.indexOf(name + '=') === 0) {
            return cookie.substring(name.length + 1);
        }
    }
    // Try to get from meta tag
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

// Helper: Show toast notification
function showToast(message, type) {
    var toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.style.cssText = 'position: fixed; top: 80px; right: 20px; z-index: 9999;';
        document.body.appendChild(toastContainer);
    }

    var toast = document.createElement('div');
    toast.className = 'toast align-items-center text-white bg-' + type + ' border-0 show';
    toast.setAttribute('role', 'alert');
    toast.innerHTML = '<div class="d-flex"><div class="toast-body">' + message + '</div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>';

    toastContainer.appendChild(toast);

    setTimeout(function() {
        toast.remove();
    }, 3000);
}
