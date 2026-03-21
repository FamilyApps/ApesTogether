// Main JavaScript file for Stock Portfolio Tracker

// Check if browser supports FaceID or Face Unlock
function checkBiometricSupport() {
    if (window.PublicKeyCredential) {
        PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable()
            .then(available => {
                if (available) {
                    console.log("Biometric authentication is supported");
                    document.querySelectorAll('.biometric-support').forEach(el => {
                        el.classList.remove('d-none');
                    });
                } else {
                    console.log("Biometric authentication is not supported");
                }
            })
            .catch(error => {
                console.error("Error checking biometric support:", error);
            });
    }
}

// Format currency values
function formatCurrency(value) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(value);
}

// Format percentage values
function formatPercentage(value) {
    return new Intl.NumberFormat('en-US', {
        style: 'percent',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value / 100);
}

// Handle form submissions with validation
function setupFormValidation() {
    const forms = document.querySelectorAll('.needs-validation');
    
    Array.from(forms).forEach(form => {
        form.addEventListener('submit', event => {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            
            form.classList.add('was-validated');
        }, false);
    });
}

// Show loading spinner
function showLoading(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = '<div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div>';
    }
}

// Hide loading spinner
function hideLoading(elementId, content) {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = content;
    }
}

// Initialize tooltips and popovers
function initTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    checkBiometricSupport();
    setupFormValidation();
    initTooltips();
    
    // Add fade-in animation to main content
    const mainContent = document.querySelector('.container');
    if (mainContent) {
        mainContent.classList.add('fade-in');
    }
});

// Handle ticker symbol validation
function validateTickerSymbol(input) {
    const tickerPattern = /^[A-Za-z]{1,5}$/;
    const isValid = tickerPattern.test(input.value);
    
    if (!isValid) {
        input.setCustomValidity('Please enter a valid ticker symbol (1-5 letters)');
    } else {
        input.setCustomValidity('');
    }
}

// Convert ticker symbols to uppercase
function convertToUppercase(input) {
    input.value = input.value.toUpperCase();
}
