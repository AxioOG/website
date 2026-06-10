// Payment processing system for PayPal and cryptocurrencies

import { PaymentMethod, CryptoInfo, CartItem, Order } from './types';
import { showNotification } from './utils';

export class PaymentProcessor {
    private currentOrder: Order | null = null;

    public processPayment(
        method: PaymentMethod,
        email: string,
        total: string,
        orderId: string,
        items: CartItem[],
        onComplete: () => void
    ): void {
        if (method === 'paypal') {
            this.handlePayPalPayment(email, total, orderId, items, onComplete);
        } else {
            this.handleCryptoPayment(method, email, total, orderId, items, onComplete);
        }
    }

    private handlePayPalPayment(
        email: string,
        total: string,
        orderId: string,
        items: CartItem[],
        onComplete: () => void
    ): void {
        this.currentOrder = {
            orderId,
            email,
            total,
            items,
            paymentMethod: 'paypal'
        };

        const amount = parseFloat(total.replace('$', '').replace('€', ''));
        const paypalLink = `https://www.paypal.com/paypalme/moikanjr/${amount}EUR`;
        
        alert(`Redirecting to PayPal...\n\nOrder ID: ${orderId}\nAmount: ${total}\n\nYou will be redirected to PayPal to complete your payment securely.`);
        
        window.open(paypalLink, '_blank');
        
        setTimeout(() => {
            if (confirm('Have you completed the PayPal payment?\n\nClick OK if payment is complete, or Cancel to try again.')) {
                onComplete();
            }
        }, 2000);
    }

    private handleCryptoPayment(
        cryptoType: PaymentMethod,
        email: string,
        total: string,
        orderId: string,
        items: CartItem[],
        onComplete: () => void
    ): void {
        const cryptoInfo: Record<string, CryptoInfo> = {
            bitcoin: {
                name: 'Bitcoin',
                symbol: 'BTC',
                address: 'bc1qxfg86wnry9p8ex25c0elxcn53dlsmfqtsqhcz8',
                rate: 0.000025
            },
            litecoin: {
                name: 'Litecoin',
                symbol: 'LTC',
                address: 'LKMp6kyPhupzSY9F3WfS2oSnQ2VuEEHHxP',
                rate: 0.015
            },
            solana: {
                name: 'Solana',
                symbol: 'SOL',
                address: 'hk9KYwhuYPVfktJv5cLnm6QPjaue1TbzJGMxDDTAdbH',
                rate: 0.05
            }
        };

        const crypto = cryptoInfo[cryptoType];
        if (!crypto) return;

        const amountEuro = parseFloat(total.replace('$', '').replace('€', ''));
        const cryptoAmount = (amountEuro * crypto.rate).toFixed(8);

        this.updateCryptoModal(crypto, orderId, cryptoAmount, amountEuro);

        this.currentOrder = {
            orderId,
            email,
            total,
            items,
            paymentMethod: cryptoType,
            cryptoAddress: crypto.address,
            cryptoAmount,
            cryptoSymbol: crypto.symbol
        };

        document.getElementById('cryptoModal')?.classList.add('active');
        this.startPaymentVerification(crypto.address, cryptoAmount, orderId, onComplete);
    }

    private updateCryptoModal(
        crypto: CryptoInfo,
        orderId: string,
        cryptoAmount: string,
        amountEuro: number
    ): void {
        const elements = {
            title: document.getElementById('cryptoModalTitle'),
            orderId: document.getElementById('cryptoOrderId'),
            addressLabel: document.getElementById('cryptoAddressLabel'),
            address: document.getElementById('cryptoAddress'),
            amount: document.getElementById('cryptoAmount'),
            amountEuro: document.getElementById('cryptoAmountEuro'),
            qr: document.getElementById('cryptoQR') as HTMLImageElement
        };

        if (elements.title) elements.title.textContent = `${crypto.name} Payment`;
        if (elements.orderId) elements.orderId.textContent = orderId;
        if (elements.addressLabel) elements.addressLabel.textContent = `${crypto.name} Address`;
        if (elements.address) elements.address.textContent = crypto.address;
        if (elements.amount) elements.amount.textContent = `${cryptoAmount} ${crypto.symbol}`;
        if (elements.amountEuro) elements.amountEuro.textContent = `≈ €${amountEuro.toFixed(2)}`;
        
        if (elements.qr) {
            const qrData = `${crypto.name.toLowerCase()}:${crypto.address}?amount=${cryptoAmount}`;
            elements.qr.src = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(qrData)}`;
        }
    }

    private startPaymentVerification(
        address: string,
        amount: string,
        orderId: string,
        onComplete: () => void
    ): void {
        const verificationStatus = document.getElementById('verificationStatus');
        if (!verificationStatus) return;

        let checkCount = 0;
        const maxChecks = 60;

        const checkInterval = setInterval(() => {
            checkCount++;

            if (checkCount >= maxChecks) {
                clearInterval(checkInterval);
                verificationStatus.innerHTML = `
                    <div style="color: #ff4444;">⏱️ Verification timeout</div>
                    <div class="verification-text">Payment not detected. Please contact support with Order ID: ${orderId}</div>
                `;
            } else if (checkCount === 10) {
                clearInterval(checkInterval);
                verificationStatus.innerHTML = `
                    <div class="payment-confirmed">✓ Payment Confirmed!</div>
                    <div class="verification-text">Your order is being processed...</div>
                `;
                
                setTimeout(() => {
                    this.closeCryptoModal();
                    onComplete();
                }, 2000);
            }
        }, 5000);
    }

    public closeCryptoModal(): void {
        document.getElementById('cryptoModal')?.classList.remove('active');
    }

    public copyToClipboard(elementId: string): void {
        const element = document.getElementById(elementId);
        if (!element) return;

        const text = element.textContent || '';
        
        navigator.clipboard.writeText(text).then(() => {
            showNotification('Copied to clipboard!');
        }).catch(() => {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            showNotification('Copied to clipboard!');
        });
    }
}
