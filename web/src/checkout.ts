// Checkout system with form validation

import { CheckboxStates, PaymentMethod } from './types';
import { ShoppingCart } from './cart';
import { PaymentProcessor } from './payments';

export class CheckoutSystem {
    private selectedPaymentMethod: PaymentMethod | null = null;
    private checkboxStates: CheckboxStates = { tos: false, promo: false };
    private cart: ShoppingCart;
    private paymentProcessor: PaymentProcessor;

    constructor(cart: ShoppingCart) {
        this.cart = cart;
        this.paymentProcessor = new PaymentProcessor();
    }

    public initialize(): void {
        const emailInput = document.getElementById('emailInput') as HTMLInputElement;
        emailInput?.addEventListener('input', () => this.validateForm());
    }

    public showCheckoutPage(): void {
        if (this.cart.isEmpty()) {
            alert('Your cart is empty!');
            return;
        }

        document.getElementById('storeSection')?.classList.remove('active');
        const hero = document.querySelector('.hero') as HTMLElement;
        if (hero) hero.style.display = 'none';
        
        const statusSection = document.querySelector('.status-section') as HTMLElement;
        if (statusSection) statusSection.style.display = 'none';
        
        document.querySelector('.payment-section')?.classList.remove('show');
        document.getElementById('checkoutPage')?.classList.add('active');
        
        this.updateOrderSummary();
        this.cart.close();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    private updateOrderSummary(): void {
        const summaryItems = document.getElementById('orderSummaryItems');
        const checkoutTotal = document.getElementById('checkoutTotal');
        
        if (!summaryItems || !checkoutTotal) return;

        const items = this.cart.getItems();
        let html = '';
        items.forEach(item => {
            html += `
                <div class="summary-item">
                    <span>${item.name}</span>
                    <span>${item.price.toFixed(2)}</span>
                </div>
            `;
        });
        
        summaryItems.innerHTML = html;
        checkoutTotal.textContent = `${this.cart.getTotal().toFixed(2)}`;
    }

    public selectPaymentMethod(method: PaymentMethod): void {
        document.querySelectorAll('.payment-option').forEach(opt => {
            opt.classList.remove('selected');
        });
        
        (event as any)?.currentTarget?.classList.add('selected');
        this.selectedPaymentMethod = method;
        this.validateForm();
    }

    public toggleCheckbox(type: 'tos' | 'promo'): void {
        const checkbox = document.getElementById(type + 'Checkbox');
        this.checkboxStates[type] = !this.checkboxStates[type];
        
        if (this.checkboxStates[type]) {
            checkbox?.classList.add('checked');
        } else {
            checkbox?.classList.remove('checked');
        }
        
        this.validateForm();
    }

    private validateForm(): void {
        const emailInput = document.getElementById('emailInput') as HTMLInputElement;
        const continueBtn = document.getElementById('continueBtn') as HTMLButtonElement;
        
        if (!emailInput || !continueBtn) return;

        const email = emailInput.value;
        
        if (email && this.selectedPaymentMethod && this.checkboxStates.tos) {
            continueBtn.disabled = false;
        } else {
            continueBtn.disabled = true;
        }
    }

    public applyCoupon(): void {
        const couponInput = document.getElementById('couponInput') as HTMLInputElement;
        const couponCode = couponInput?.value.trim();
        
        if (!couponCode) {
            alert('Please enter a coupon code');
            return;
        }
        
        const coupons: Record<string, number> = {
            'WELCOME10': 0.10,
            'SAVE20': 0.20,
            'VIP50': 0.50
        };
        
        const discount = coupons[couponCode.toUpperCase()];
        if (discount) {
            const total = this.cart.getTotal();
            const newTotal = total * (1 - discount);
            
            const checkoutTotal = document.getElementById('checkoutTotal');
            if (checkoutTotal) {
                checkoutTotal.textContent = `${newTotal.toFixed(2)}`;
            }
            
            const notification = `Coupon applied! ${(discount * 100)}% discount`;
            this.showNotification(notification);
        } else {
            alert('Invalid coupon code');
        }
    }

    public proceedToPayment(): void {
        const emailInput = document.getElementById('emailInput') as HTMLInputElement;
        const checkoutTotal = document.getElementById('checkoutTotal');
        
        if (!emailInput || !checkoutTotal || !this.selectedPaymentMethod) return;

        const email = emailInput.value;
        const total = checkoutTotal.textContent || '0';
        const orderId = 'MB-' + Date.now();
        
        this.paymentProcessor.processPayment(
            this.selectedPaymentMethod,
            email,
            total,
            orderId,
            this.cart.getItems(),
            () => this.completeOrder(orderId)
        );
    }

    private completeOrder(orderId: string): void {
        this.cart.clear();
        this.selectedPaymentMethod = null;
        this.checkboxStates = { tos: false, promo: false };
        
        const emailInput = document.getElementById('emailInput') as HTMLInputElement;
        const couponInput = document.getElementById('couponInput') as HTMLInputElement;
        if (emailInput) emailInput.value = '';
        if (couponInput) couponInput.value = '';
        
        document.getElementById('tosCheckbox')?.classList.remove('checked');
        document.getElementById('promoCheckbox')?.classList.remove('checked');
        document.querySelectorAll('.payment-option').forEach(opt => opt.classList.remove('selected'));
        
        document.getElementById('checkoutPage')?.classList.remove('active');
        
        const hero = document.querySelector('.hero') as HTMLElement;
        const statusSection = document.querySelector('.status-section') as HTMLElement;
        if (hero) hero.style.display = 'block';
        if (statusSection) statusSection.style.display = 'block';
        
        const nav = document.querySelectorAll('.nav-links a');
        nav.forEach(l => l.classList.remove('active'));
        document.querySelector('.nav-links a[href="#home"]')?.classList.add('active');
        
        this.showNotification(`Order ${orderId} confirmed! Check your email for details.`);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    private showNotification(message: string): void {
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            top: 100px;
            right: 20px;
            background: rgba(255, 255, 255, 0.9);
            color: black;
            padding: 1rem 2rem;
            border-radius: 10px;
            z-index: 10000;
            animation: slideIn 0.3s ease;
        `;
        notification.textContent = message;
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => notification.remove(), 300);
        }, 2000);
    }
}
