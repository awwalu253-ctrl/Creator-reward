// ====================
// MAIN JAVASCRIPT
// ====================

// Auto-dismiss flash messages after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const flashMessages = document.querySelectorAll('.flash');
    flashMessages.forEach((flash, index) => {
        setTimeout(() => {
            flash.style.opacity = '0';
            flash.style.transform = 'translateX(100%)';
            setTimeout(() => {
                flash.remove();
            }, 300);
        }, 5000 + (index * 1000));
    });
});

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
        const href = this.getAttribute('href');
        if (href === '#') return;
        
        e.preventDefault();
        const target = document.querySelector(href);
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Close flash messages on click
document.querySelectorAll('.flash-close').forEach(btn => {
    btn.addEventListener('click', function() {
        this.parentElement.style.opacity = '0';
        setTimeout(() => {
            this.parentElement.remove();
        }, 300);
    });
});

// Track page views
document.addEventListener('DOMContentLoaded', function() {
    // Simple analytics tracking - just log
    console.log('Page loaded:', window.location.pathname);
});

// ====================
// UTILITY FUNCTIONS
// ====================
function formatCurrency(amount, currency = 'USD') {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: currency
    }).format(amount);
}

function generateId(length = 8) {
    return Math.random().toString(36).substring(2, length + 2).toUpperCase();
}

function isValidEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

function isValidPhone(phone) {
    const re = /^[\+\d\s\-\(\)]{10,}$/;
    return re.test(phone);
}