// Shopping cart management system

import { CartItem } from './types';
import { showNotification } from './utils';

export class ShoppingCart {
    private cart: CartItem[] = [];
    private cartContainer: HTMLElement | null;
    private cartItems: HTMLElement | null;
    private cartBadge: HTMLElement | null;
    private cartTotal: HTMLElement | null;

    constructor() {
        this.cartContainer = document.getElementById('cartContainer');
        this.cartItems = document.getElementById('cartItems');
        this.cartBadge = document.getElementById('cartBadge');
        this.cartTotal = document.getElementById('cartTotal');
    }

    public addItem(productName: string, price: number): void {
        this.cart.push({ name: productName, price });
        this.update();
        showNotification(`${productName} added to cart!`);
    }

    public removeItem(index: number): void {
        this.cart.splice(index, 1);
        this.update();
    }

    public update(): void {
        if (!this.cartItems || !this.cartBadge || !this.cartTotal) return;

        if (this.cart.length === 0) {
            this.cartItems.innerHTML = `
                <div class="empty-cart">
                    <i class="fas fa-shopping-cart"></i>
                    <p>Your cart is empty</p>
                </div>
            `;
            this.cartBadge.style.display = 'none';
        } else {
            this.cartItems.innerHTML = this.cart.map((item, index) => `
                <div class="cart-item">
                    <div class="cart-item-info">
                        <div class="cart-item-name">${item.name}</div>
                        <div class="cart-item-price">${item.price.toFixed(2)}</div>
                    </div>
                    <button class="remove-item" onclick="window.cart.removeItem(${index})">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `).join('');
            
            this.cartBadge.textContent = this.cart.length.toString();
            this.cartBadge.style.display = 'flex';
        }

        const total = this.cart.reduce((sum, item) => sum + item.price, 0);
        this.cartTotal.textContent = `${total.toFixed(2)}`;
    }

    public toggle(): void {
        this.cartContainer?.classList.toggle('open');
    }

    public close(): void {
        this.cartContainer?.classList.remove('open');
    }

    public getItems(): CartItem[] {
        return [...this.cart];
    }

    public getTotal(): number {
        return this.cart.reduce((sum, item) => sum + item.price, 0);
    }

    public clear(): void {
        this.cart = [];
        this.update();
    }

    public isEmpty(): boolean {
        return this.cart.length === 0;
    }
}
