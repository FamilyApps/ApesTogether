// Subscription handling with Apple Pay integration
document.addEventListener('DOMContentLoaded', function() {
    // Only initialize if we're on a page with subscription functionality
    const paymentRequestButton = document.getElementById('payment-request-button');
    if (!paymentRequestButton) return;
    
    // Get data from data attributes
    const stripePublicKey = paymentRequestButton.getAttribute('data-stripe-key');
    const userId = paymentRequestButton.getAttribute('data-user-id');
    const price = parseFloat(paymentRequestButton.getAttribute('data-price'));
    const username = paymentRequestButton.getAttribute('data-username');
    
    if (!stripePublicKey || !userId || !price) {
        console.error('Missing required subscription data');
        return;
    }
    
    // Initialize Stripe
    const stripe = Stripe(stripePublicKey, {
        apiVersion: '2020-08-27'
    });
    
    // Check if Payment Request is available (Apple Pay, Google Pay, etc)
    const paymentRequest = stripe.paymentRequest({
        country: 'US',
        currency: 'usd',
        total: {
            label: `Subscription to ${username}'s Portfolio`,
            amount: Math.round(price * 100), // Amount in cents
        },
        requestPayerName: true,
        requestPayerEmail: true,
    });
    
    // Check if the Payment Request is available
    paymentRequest.canMakePayment().then(function(result) {
        if (result && (result.applePay || result.googlePay)) {
            // Create and mount the Payment Request Button
            const elements = stripe.elements();
            const prButton = elements.create('paymentRequestButton', {
                paymentRequest: paymentRequest,
                style: {
                    paymentRequestButton: {
                        type: 'subscribe', // 'default', 'donate', or 'buy'
                        theme: 'dark',
                        height: '48px'
                    },
                },
            });
            
            // Mount the button
            prButton.mount('#payment-request-button');
        } else {
            // Hide the payment request button if Apple Pay/Google Pay is not available
            paymentRequestButton.style.display = 'none';
        }
    });
    
    // Handle the payment request completion
    paymentRequest.on('paymentmethod', function(ev) {
        // Create the payment intent on the server
        fetch('/create-payment-intent', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_id: userId
            })
        })
        .then(function(response) {
            return response.json();
        })
        .then(function(data) {
            if (data.error) {
                // Show error and complete the payment request
                ev.complete('fail');
                alert('Payment failed: ' + data.error);
                return;
            }
            
            // Confirm the PaymentIntent with the payment method
            stripe.confirmCardPayment(
                data.clientSecret,
                {payment_method: ev.paymentMethod.id},
                {handleActions: false}
            ).then(function(confirmResult) {
                if (confirmResult.error) {
                    // Report to the browser that the payment failed
                    ev.complete('fail');
                    
                    // Check if additional authentication is needed
                    if (confirmResult.error.code === 'authentication_required') {
                        // Redirect to the payment confirmation page for additional authentication
                        window.location.href = `/payment-confirmation?payment_intent_client_secret=${data.clientSecret}&subscription_id=${data.subscriptionId}&user_id=${userId}`;
                    } else {
                        alert('Payment confirmation failed: ' + confirmResult.error.message);
                    }
                } else {
                    // Report to the browser that the confirmation was successful
                    ev.complete('success');
                    
                    // Redirect to the success page
                    window.location.href = `/subscription-success?subscription_id=${data.subscriptionId}`;
                }
            });
        })
        .catch(function(error) {
            console.error('Error:', error);
            ev.complete('fail');
        });
    });
});
