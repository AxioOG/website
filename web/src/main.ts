// Main application entry point

import { ParticleSystem } from './particles';
import { Navigation } from './navigation';
import { ShoppingCart } from './cart';
import { CheckoutSystem } from './checkout';
import { PaymentProcessor } from './payments';

class FuseApp {
    private particleSystem: ParticleSystem;
    private navigation: Navigation;
    private cart: ShoppingCart;
    private checkout: CheckoutSystem;
    private paymentProcessor: PaymentProcessor;

    constructor() {
        this.particleSystem = new ParticleSystem('particles');
        this.navigation = new Navigation();
        this.cart = new ShoppingCart();
        this.checkout = new CheckoutSystem(this.cart);
        this.paymentProcessor = new PaymentProcessor();
    }

    public initialize(): void {
        document.addEventListener('DOMContentLoaded', () => {
            this.particleSystem.initialize();
            this.navigation.initialize();
            this.checkout.initialize();
            this.setupEventListeners();
        });

        window.addEventListener('resize', () => {
            this.particleSystem.recreate();
        });
    }

    private setupEventListeners(): void {
        // Expose cart methods globally for onclick handlers
        (window as any).cart = this.cart;
        (window as any).toggleCart = () => this.cart.toggle();
        (window as any).addToCart = (name: string, price: number) => this.cart.addItem(name, price);
        (window as any).removeFromCart = (index: number) => this.cart.removeItem(index);
        (window as any).checkout = () => this.checkout.showCheckoutPage();

        // Expose checkout methods
        (window as any).selectPaymentMethod = (method: string) => this.checkout.selectPaymentMethod(method as any);
        (window as any).toggleCheckbox = (type: string) => this.checkout.toggleCheckbox(type as any);
        (window as any).applyCoupon = () => this.checkout.applyCoupon();
        (window as any).proceedToPayment = () => this.checkout.proceedToPayment();

        // Expose payment methods
        (window as any).closeCryptoModal = () => this.paymentProcessor.closeCryptoModal();
        (window as any).copyToClipboard = (id: string) => this.paymentProcessor.copyToClipboard(id);

        // Legacy payment selection (not used anymore)
        (window as any).selectPayment = () => {
            alert('Please use the checkout process to complete your purchase.');
        };
    }
}

// Initialize the application
const app = new FuseApp();
app.initialize();
