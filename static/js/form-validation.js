// ====================
// FORM VALIDATION
// ====================

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('claimForm');
    if (!form) return;
    
    const submitBtn = document.getElementById('submitBtn');
    
    // Real-time validation on blur
    const inputs = form.querySelectorAll('input, select, textarea');
    inputs.forEach(input => {
        input.addEventListener('blur', function() {
            validateField(this);
        });
        
        input.addEventListener('input', function() {
            if (this.dataset.validated) {
                validateField(this);
            }
        });
    });
    
    // Form submission
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        
        let isValid = true;
        const inputs = this.querySelectorAll('input[required], select[required], textarea[required]');
        inputs.forEach(input => {
            if (!validateField(input)) {
                isValid = false;
            }
        });
        
        // Check privacy consent
        const privacyCheck = document.getElementById('privacy_consent');
        if (privacyCheck && !privacyCheck.checked) {
            showError(privacyCheck, 'Please agree to the Privacy Policy and Terms');
            isValid = false;
        }
        
        if (isValid) {
            // Disable button to prevent double submission
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Submitting...';
            this.submit();
        }
    });
});

function validateField(field) {
    const errorEl = document.querySelector(`[data-error="${field.id}"]`);
    const group = field.closest('.form-group');
    let isValid = true;
    let errorMessage = '';
    
    // Remove existing error state
    if (group) group.classList.remove('error');
    if (errorEl) errorEl.textContent = '';
    
    // Skip validation if field is hidden or disabled
    if (field.disabled || field.type === 'hidden') return true;
    
    // Check if required but empty
    if (field.hasAttribute('required') && !field.value.trim()) {
        isValid = false;
        errorMessage = 'This field is required';
    }
    
    // Email validation
    if (field.type === 'email' && field.value.trim()) {
        if (!isValidEmail(field.value.trim())) {
            isValid = false;
            errorMessage = 'Please enter a valid email address';
        }
    }
    
    // Phone validation
    if (field.id === 'phone' && field.value.trim()) {
        if (!isValidPhone(field.value.trim())) {
            isValid = false;
            errorMessage = 'Please enter a valid phone number';
        }
    }
    
    // Postal code validation (basic)
    if (field.id === 'postal_code' && field.value.trim()) {
        if (field.value.trim().length < 3) {
            isValid = false;
            errorMessage = 'Please enter a valid postal code';
        }
    }
    
    // Show error if invalid
    if (!isValid) {
        if (group) group.classList.add('error');
        if (errorEl) errorEl.textContent = errorMessage;
        field.dataset.validated = 'false';
    } else {
        field.dataset.validated = 'true';
    }
    
    return isValid;
}

function showError(field, message) {
    const group = field.closest('.form-group');
    const errorEl = document.querySelector(`[data-error="${field.id}"]`);
    
    if (group) group.classList.add('error');
    if (errorEl) errorEl.textContent = message;
}