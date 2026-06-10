// Type definitions for Fuse.gg

export interface CartItem {
    name: string;
    price: number;
}

export interface Order {
    orderId: string;
    email: string;
    total: string;
    items: CartItem[];
    paymentMethod: string;
    cryptoAddress?: string;
    cryptoAmount?: string;
    cryptoSymbol?: string;
}

export interface CryptoInfo {
    name: string;
    symbol: string;
    address: string;
    rate: number;
}

export interface PaymentInfo {
    name: string;
    email?: string;
    address?: string;
    tag?: string;
    username?: string;
    link?: string;
    instructions: string;
}

export interface CheckboxStates {
    tos: boolean;
    promo: boolean;
}

export interface Particle {
    element: HTMLElement;
    x: number;
    y: number;
    originalX: number;
    originalY: number;
}

export type PaymentMethod = 'paypal' | 'bitcoin' | 'litecoin' | 'solana';

// Ticket System Types

export enum TicketStatus {
    OPEN = 'open',
    IN_PROGRESS = 'in_progress',
    WAITING_FOR_RESPONSE = 'waiting_for_response',
    RESOLVED = 'resolved',
    CLOSED = 'closed'
}

export enum TicketCategory {
    GENERAL = 'general',
    BAN_APPEAL = 'ban_appeal',
    STRIPE = 'stripe',
    CRYPTO = 'crypto',
    PARTNERSHIP = 'partnership',
    TECHNICAL_SUPPORT = 'technical_support'
}

export interface Ticket {
    id: string;
    userId: string;
    subject: string;
    description?: string;
    status: TicketStatus;
    category: TicketCategory;
    createdAt: Date;
    updatedAt: Date;
    lastReplyAt?: Date;
    assignedTo?: string;
    participants: string[];
    messageCount: number;
    tags: string[];
}

export interface TicketReply {
    id: string;
    ticketId: string;
    authorId: string;
    authorName: string;
    authorAvatar?: string;
    message: string;
    createdAt: Date;
    isStaff: boolean;
    attachments?: TicketAttachment[];
}

export interface TicketAttachment {
    id: string;
    filename: string;
    url: string;
    size: number;
    mimeType: string;
    uploadedAt: Date;
}

export interface TicketHistoryEntry {
    id: string;
    ticketId: string;
    action: string;
    description: string;
    performedBy: string;
    performedAt: Date;
    metadata?: Record<string, any>;
}

export interface TicketMember {
    userId: string;
    username: string;
    displayName: string;
    avatar?: string;
    isStaff: boolean;
    joinedAt: Date;
}

export interface TicketDetails extends Ticket {
    replies: TicketReply[];
    attachments: TicketAttachment[];
    history: TicketHistoryEntry[];
    members: TicketMember[];
}

export interface CreateTicketRequest {
    subject: string;
    category: TicketCategory;
    description?: string;
    attachments?: File[];
}

export interface TicketUpdate {
    status?: TicketStatus;
    assignedTo?: string;
    updatedAt?: Date;
    lastReplyAt?: Date;
    messageCount?: number;
}

export interface TicketFilters {
    status?: TicketStatus;
    category?: TicketCategory;
    dateFrom?: Date;
    dateTo?: Date;
    assignedTo?: string;
}

// Category display information matching UI design
export const CATEGORY_INFO = {
    [TicketCategory.GENERAL]: {
        emoji: '🔧',
        title: 'General',
        description: 'General inquiries (not listed below)'
    },
    [TicketCategory.BAN_APPEAL]: {
        emoji: '⚡',
        title: 'Ban Appeal',
        description: 'Appeal an account restriction'
    },
    [TicketCategory.STRIPE]: {
        emoji: '💳',
        title: 'Stripe',
        description: 'Stripe billing inquiries'
    },
    [TicketCategory.CRYPTO]: {
        emoji: '₿',
        title: 'Crypto',
        description: 'Crypto billing inquiries'
    },
    [TicketCategory.PARTNERSHIP]: {
        emoji: '🤝',
        title: 'Partnership',
        description: 'Partnership inquiries'
    },
    [TicketCategory.TECHNICAL_SUPPORT]: {
        emoji: '🔧',
        title: 'Technical Support',
        description: 'Report or request assistance with technical issues'
    }
} as const;
