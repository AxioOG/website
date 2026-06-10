// TicketAPI Service - Handles all ticket data operations and Discord API integration

import { 
    Ticket, 
    TicketDetails, 
    CreateTicketRequest, 
    TicketReply,
    TicketAttachment,
    TicketHistoryEntry,
    TicketMember,
    TicketUpdate,
    TicketStatus, 
    TicketCategory,
    TicketFilters
} from './types';

/**
 * Service layer for ticket data operations and Discord API integration
 * Handles CRUD operations, local storage persistence, and data validation
 */
export class TicketAPI {
    private readonly STORAGE_KEYS = {
        TICKETS: 'fuse_tickets',
        REPLIES: 'fuse_ticket_replies',
        ATTACHMENTS: 'fuse_ticket_attachments',
        HISTORY: 'fuse_ticket_history',
        BACKUP: 'fuse_tickets_backup'
    };

    private readonly RATE_LIMIT = {
        MAX_TICKETS_PER_HOUR: 5,
        RATE_LIMIT_KEY: 'fuse_ticket_rate_limit'
    };

    constructor() {
        this.initializeStorage();
    }

    /**
     * Get all tickets for a specific user
     * @param userId - Discord user ID
     * @returns Promise resolving to array of user's tickets
     */
    public async getUserTickets(userId: string): Promise<Ticket[]> {
        try {
            this.validateUserId(userId);
            
            const allTickets = this.getStoredTickets();
            const userTickets = allTickets.filter(ticket => ticket.userId === userId);
            
            // Sort by creation date (newest first)
            return userTickets.sort((a, b) => 
                new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
            );
        } catch (error) {
            console.error('Error getting user tickets:', error);
            throw new Error('Failed to retrieve tickets');
        }
    }

    /**
     * Create a new ticket
     * @param request - Ticket creation request data
     * @returns Promise resolving to the created ticket
     */
    public async createTicket(request: CreateTicketRequest): Promise<Ticket> {
        try {
            // Validate request data
            this.validateCreateTicketRequest(request);
            
            // Check rate limiting
            await this.checkRateLimit();
            
            // Get current user info
            const currentUser = this.getCurrentUser();
            
            // Generate unique ticket ID
            const ticketId = this.generateTicketId();
            
            // Create ticket object
            const newTicket: Ticket = {
                id: ticketId,
                userId: currentUser.id,
                subject: request.subject.trim(),
                description: request.description?.trim(),
                status: TicketStatus.OPEN,
                category: request.category,
                createdAt: new Date(),
                updatedAt: new Date(),
                lastReplyAt: undefined,
                assignedTo: undefined,
                participants: [currentUser.id],
                messageCount: 0,
                tags: []
            };

            // Save ticket to storage
            await this.saveTicket(newTicket);
            
            // Create initial history entry
            await this.addHistoryEntry(ticketId, 'created', 'Ticket created', currentUser.id);
            
            // Update rate limiting
            this.updateRateLimit();
            
            return newTicket;
        } catch (error) {
            console.error('Error creating ticket:', error);
            throw error;
        }
    }

    /**
     * Get detailed information for a specific ticket
     * @param ticketId - ID of the ticket to retrieve
     * @returns Promise resolving to ticket details
     */
    public async getTicketDetails(ticketId: string): Promise<TicketDetails> {
        try {
            this.validateTicketId(ticketId);
            
            const ticket = await this.getTicketById(ticketId);
            if (!ticket) {
                throw new Error('Ticket not found');
            }

            // Verify user has access to this ticket
            const currentUser = this.getCurrentUser();
            if (!this.hasTicketAccess(ticket, currentUser.id)) {
                throw new Error('Access denied');
            }

            // Get related data
            const replies = await this.getTicketReplies(ticketId);
            const attachments = await this.getTicketAttachments(ticketId);
            const history = await this.getTicketHistory(ticketId);
            const members = await this.getTicketMembers(ticket);

            return {
                ...ticket,
                replies,
                attachments,
                history,
                members
            };
        } catch (error) {
            console.error('Error getting ticket details:', error);
            throw error;
        }
    }

    /**
     * Update an existing ticket
     * @param ticketId - ID of the ticket to update
     * @param updates - Updates to apply to the ticket
     */
    public async updateTicket(ticketId: string, updates: TicketUpdate): Promise<void> {
        try {
            this.validateTicketId(ticketId);
            
            const ticket = await this.getTicketById(ticketId);
            if (!ticket) {
                throw new Error('Ticket not found');
            }

            // Verify user has access to this ticket
            const currentUser = this.getCurrentUser();
            if (!this.hasTicketAccess(ticket, currentUser.id)) {
                throw new Error('Access denied');
            }

            // Validate status transitions
            if (updates.status && !this.isValidStatusTransition(ticket.status, updates.status, false)) {
                throw new Error('Invalid status transition');
            }

            // Apply updates
            const updatedTicket: Ticket = {
                ...ticket,
                ...updates,
                updatedAt: new Date()
            };

            // Save updated ticket
            await this.saveTicketUpdate(updatedTicket);
            
            // Add history entry for status changes
            if (updates.status && updates.status !== ticket.status) {
                await this.addHistoryEntry(
                    ticketId, 
                    'status_changed', 
                    `Status changed from ${ticket.status} to ${updates.status}`,
                    currentUser.id
                );
            }
        } catch (error) {
            console.error('Error updating ticket:', error);
            throw error;
        }
    }

    /**
     * Add a reply to a ticket
     * @param ticketId - ID of the ticket to reply to
     * @param reply - Reply data
     */
    public async addReply(ticketId: string, reply: Omit<TicketReply, 'id' | 'createdAt'>): Promise<void> {
        try {
            this.validateTicketId(ticketId);
            this.validateReplyMessage(reply.message);
            
            const ticket = await this.getTicketById(ticketId);
            if (!ticket) {
                throw new Error('Ticket not found');
            }

            // Verify user has access to this ticket
            const currentUser = this.getCurrentUser();
            if (!this.hasTicketAccess(ticket, currentUser.id)) {
                throw new Error('Access denied');
            }

            // Create reply object
            const newReply: TicketReply = {
                ...reply,
                id: this.generateReplyId(),
                createdAt: new Date()
            };

            // Save reply
            await this.saveReply(newReply);
            
            // Update ticket metadata
            await this.updateTicket(ticketId, {
                lastReplyAt: new Date(),
                messageCount: ticket.messageCount + 1,
                // Update status if ticket was resolved and user is replying
                status: ticket.status === TicketStatus.RESOLVED && !reply.isStaff 
                    ? TicketStatus.WAITING_FOR_RESPONSE 
                    : ticket.status
            });

            // Add history entry
            await this.addHistoryEntry(
                ticketId,
                'reply_added',
                `Reply added by ${reply.authorName}`,
                reply.authorId
            );
        } catch (error) {
            console.error('Error adding reply:', error);
            throw error;
        }
    }

    /**
     * Delete a ticket (soft delete - mark as closed)
     * @param ticketId - ID of the ticket to delete
     */
    public async deleteTicket(ticketId: string): Promise<void> {
        try {
            this.validateTicketId(ticketId);
            
            const ticket = await this.getTicketById(ticketId);
            if (!ticket) {
                throw new Error('Ticket not found');
            }

            // Verify user has access to this ticket
            const currentUser = this.getCurrentUser();
            if (!this.hasTicketAccess(ticket, currentUser.id)) {
                throw new Error('Access denied');
            }

            // Soft delete by marking as closed
            await this.updateTicket(ticketId, {
                status: TicketStatus.CLOSED
            });

            // Add history entry
            await this.addHistoryEntry(
                ticketId,
                'ticket_closed',
                'Ticket closed by user',
                currentUser.id
            );
        } catch (error) {
            console.error('Error deleting ticket:', error);
            throw error;
        }
    }

    /**
     * Search tickets by query string
     * @param userId - User ID to search within
     * @param query - Search query
     * @returns Promise resolving to matching tickets
     */
    public async searchTickets(userId: string, query: string): Promise<Ticket[]> {
        try {
            this.validateUserId(userId);
            
            if (!query.trim()) {
                return this.getUserTickets(userId);
            }

            const userTickets = await this.getUserTickets(userId);
            const searchTerm = query.toLowerCase().trim();
            
            return userTickets.filter(ticket => 
                ticket.subject.toLowerCase().includes(searchTerm) ||
                ticket.description?.toLowerCase().includes(searchTerm) ||
                ticket.id.toLowerCase().includes(searchTerm) ||
                ticket.tags.some(tag => tag.toLowerCase().includes(searchTerm))
            );
        } catch (error) {
            console.error('Error searching tickets:', error);
            throw error;
        }
    }

    /**
     * Get tickets filtered by status
     * @param userId - User ID to filter within
     * @param status - Status to filter by
     * @returns Promise resolving to filtered tickets
     */
    public async getTicketsByStatus(userId: string, status: TicketStatus): Promise<Ticket[]> {
        try {
            this.validateUserId(userId);
            
            const userTickets = await this.getUserTickets(userId);
            return userTickets.filter(ticket => ticket.status === status);
        } catch (error) {
            console.error('Error getting tickets by status:', error);
            throw error;
        }
    }

    /**
     * Get tickets filtered by category
     * @param userId - User ID to filter within
     * @param category - Category to filter by
     * @returns Promise resolving to filtered tickets
     */
    public async getTicketsByCategory(userId: string, category: TicketCategory): Promise<Ticket[]> {
        try {
            this.validateUserId(userId);
            
            const userTickets = await this.getUserTickets(userId);
            return userTickets.filter(ticket => ticket.category === category);
        } catch (error) {
            console.error('Error getting tickets by category:', error);
            throw error;
        }
    }

    /**
     * Backup ticket data to separate storage
     * @returns Promise resolving when backup is complete
     */
    public async backupTicketData(): Promise<void> {
        try {
            const backupData = {
                tickets: this.getStoredTickets(),
                replies: this.getStoredReplies(),
                attachments: this.getStoredAttachments(),
                history: this.getStoredHistory(),
                timestamp: new Date().toISOString()
            };

            localStorage.setItem(this.STORAGE_KEYS.BACKUP, JSON.stringify(backupData));
            console.log('Ticket data backup completed');
        } catch (error) {
            console.error('Error backing up ticket data:', error);
            throw new Error('Failed to backup ticket data');
        }
    }

    /**
     * Restore ticket data from backup
     * @returns Promise resolving when restore is complete
     */
    public async restoreTicketData(): Promise<void> {
        try {
            const backupData = localStorage.getItem(this.STORAGE_KEYS.BACKUP);
            if (!backupData) {
                throw new Error('No backup data found');
            }

            const backup = JSON.parse(backupData);
            
            // Validate backup data structure
            if (!backup.tickets || !backup.replies || !backup.attachments || !backup.history) {
                throw new Error('Invalid backup data structure');
            }

            // Restore data
            localStorage.setItem(this.STORAGE_KEYS.TICKETS, JSON.stringify(backup.tickets));
            localStorage.setItem(this.STORAGE_KEYS.REPLIES, JSON.stringify(backup.replies));
            localStorage.setItem(this.STORAGE_KEYS.ATTACHMENTS, JSON.stringify(backup.attachments));
            localStorage.setItem(this.STORAGE_KEYS.HISTORY, JSON.stringify(backup.history));

            console.log('Ticket data restored from backup');
        } catch (error) {
            console.error('Error restoring ticket data:', error);
            throw error;
        }
    }

    // Private helper methods

    /**
     * Initialize storage with default values if needed
     */
    private initializeStorage(): void {
        const storageKeys = Object.values(this.STORAGE_KEYS);
        storageKeys.forEach(key => {
            if (!localStorage.getItem(key)) {
                localStorage.setItem(key, JSON.stringify([]));
            }
        });
    }

    /**
     * Get current authenticated user from Discord data
     */
    private getCurrentUser(): { id: string; username: string; avatar?: string } {
        const discordUser = localStorage.getItem('discord_user');
        if (!discordUser) {
            throw new Error('User not authenticated');
        }
        
        const user = JSON.parse(discordUser);
        return {
            id: user.id,
            username: user.username || user.global_name || 'Unknown User',
            avatar: user.avatar ? `https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png` : undefined
        };
    }

    /**
     * Generate unique ticket ID
     */
    private generateTicketId(): string {
        const timestamp = Date.now();
        const random = Math.random().toString(36).substr(2, 9);
        return `TKT-${timestamp}-${random}`.toUpperCase();
    }

    /**
     * Generate unique reply ID
     */
    private generateReplyId(): string {
        const timestamp = Date.now();
        const random = Math.random().toString(36).substr(2, 9);
        return `RPL-${timestamp}-${random}`.toUpperCase();
    }

    /**
     * Validate user ID format
     */
    private validateUserId(userId: string): void {
        if (!userId || typeof userId !== 'string' || userId.trim().length === 0) {
            throw new Error('Invalid user ID');
        }
    }

    /**
     * Validate ticket ID format
     */
    private validateTicketId(ticketId: string): void {
        if (!ticketId || typeof ticketId !== 'string' || ticketId.trim().length === 0) {
            throw new Error('Invalid ticket ID');
        }
    }

    /**
     * Validate create ticket request data
     */
    private validateCreateTicketRequest(request: CreateTicketRequest): void {
        if (!request.subject || request.subject.trim().length < 5 || request.subject.trim().length > 100) {
            throw new Error('Subject must be between 5 and 100 characters');
        }

        if (!Object.values(TicketCategory).includes(request.category)) {
            throw new Error('Invalid ticket category');
        }

        if (request.description && request.description.length > 2000) {
            throw new Error('Description cannot exceed 2000 characters');
        }

        if (request.attachments && request.attachments.length > 5) {
            throw new Error('Maximum 5 attachments allowed');
        }
    }

    /**
     * Validate reply message content
     */
    private validateReplyMessage(message: string): void {
        if (!message || message.trim().length === 0) {
            throw new Error('Reply message cannot be empty');
        }

        if (message.length > 1000) {
            throw new Error('Reply message cannot exceed 1000 characters');
        }
    }

    /**
     * Check if user has access to a ticket
     */
    private hasTicketAccess(ticket: Ticket, userId: string): boolean {
        return ticket.userId === userId || ticket.participants.includes(userId);
    }

    /**
     * Validate status transition
     */
    private isValidStatusTransition(currentStatus: TicketStatus, newStatus: TicketStatus, isStaff: boolean): boolean {
        // Users can only close resolved tickets
        if (!isStaff) {
            return currentStatus === TicketStatus.RESOLVED && newStatus === TicketStatus.CLOSED;
        }

        // Staff can make any valid transition
        const validTransitions: Record<TicketStatus, TicketStatus[]> = {
            [TicketStatus.OPEN]: [TicketStatus.IN_PROGRESS, TicketStatus.WAITING_FOR_RESPONSE, TicketStatus.RESOLVED, TicketStatus.CLOSED],
            [TicketStatus.IN_PROGRESS]: [TicketStatus.WAITING_FOR_RESPONSE, TicketStatus.RESOLVED, TicketStatus.CLOSED],
            [TicketStatus.WAITING_FOR_RESPONSE]: [TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.CLOSED],
            [TicketStatus.RESOLVED]: [TicketStatus.CLOSED, TicketStatus.WAITING_FOR_RESPONSE],
            [TicketStatus.CLOSED]: [] // Closed tickets cannot be reopened
        };

        return validTransitions[currentStatus]?.includes(newStatus) || false;
    }

    /**
     * Check rate limiting for ticket creation
     */
    private async checkRateLimit(): Promise<void> {
        const rateLimitData = localStorage.getItem(this.RATE_LIMIT.RATE_LIMIT_KEY);
        if (!rateLimitData) {
            return; // No previous rate limit data
        }

        const { count, timestamp } = JSON.parse(rateLimitData);
        const oneHourAgo = Date.now() - (60 * 60 * 1000);

        if (timestamp > oneHourAgo && count >= this.RATE_LIMIT.MAX_TICKETS_PER_HOUR) {
            throw new Error('Rate limit exceeded. Maximum 5 tickets per hour allowed.');
        }
    }

    /**
     * Update rate limiting counter
     */
    private updateRateLimit(): void {
        const rateLimitData = localStorage.getItem(this.RATE_LIMIT.RATE_LIMIT_KEY);
        const now = Date.now();
        const oneHourAgo = now - (60 * 60 * 1000);

        let count = 1;
        if (rateLimitData) {
            const existing = JSON.parse(rateLimitData);
            if (existing.timestamp > oneHourAgo) {
                count = existing.count + 1;
            }
        }

        localStorage.setItem(this.RATE_LIMIT.RATE_LIMIT_KEY, JSON.stringify({
            count,
            timestamp: now
        }));
    }

    // Storage methods

    /**
     * Get all stored tickets
     */
    private getStoredTickets(): Ticket[] {
        const stored = localStorage.getItem(this.STORAGE_KEYS.TICKETS);
        return stored ? JSON.parse(stored).map((ticket: any) => ({
            ...ticket,
            createdAt: new Date(ticket.createdAt),
            updatedAt: new Date(ticket.updatedAt),
            lastReplyAt: ticket.lastReplyAt ? new Date(ticket.lastReplyAt) : undefined
        })) : [];
    }

    /**
     * Get all stored replies
     */
    private getStoredReplies(): TicketReply[] {
        const stored = localStorage.getItem(this.STORAGE_KEYS.REPLIES);
        return stored ? JSON.parse(stored).map((reply: any) => ({
            ...reply,
            createdAt: new Date(reply.createdAt)
        })) : [];
    }

    /**
     * Get all stored attachments
     */
    private getStoredAttachments(): TicketAttachment[] {
        const stored = localStorage.getItem(this.STORAGE_KEYS.ATTACHMENTS);
        return stored ? JSON.parse(stored).map((attachment: any) => ({
            ...attachment,
            uploadedAt: new Date(attachment.uploadedAt)
        })) : [];
    }

    /**
     * Get all stored history entries
     */
    private getStoredHistory(): TicketHistoryEntry[] {
        const stored = localStorage.getItem(this.STORAGE_KEYS.HISTORY);
        return stored ? JSON.parse(stored).map((entry: any) => ({
            ...entry,
            performedAt: new Date(entry.performedAt)
        })) : [];
    }

    /**
     * Get ticket by ID
     */
    private async getTicketById(ticketId: string): Promise<Ticket | null> {
        const tickets = this.getStoredTickets();
        return tickets.find(ticket => ticket.id === ticketId) || null;
    }

    /**
     * Save a new ticket
     */
    private async saveTicket(ticket: Ticket): Promise<void> {
        const tickets = this.getStoredTickets();
        tickets.push(ticket);
        localStorage.setItem(this.STORAGE_KEYS.TICKETS, JSON.stringify(tickets));
    }

    /**
     * Save ticket update
     */
    private async saveTicketUpdate(updatedTicket: Ticket): Promise<void> {
        const tickets = this.getStoredTickets();
        const index = tickets.findIndex(ticket => ticket.id === updatedTicket.id);
        
        if (index === -1) {
            throw new Error('Ticket not found for update');
        }

        tickets[index] = updatedTicket;
        localStorage.setItem(this.STORAGE_KEYS.TICKETS, JSON.stringify(tickets));
    }

    /**
     * Save a reply
     */
    private async saveReply(reply: TicketReply): Promise<void> {
        const replies = this.getStoredReplies();
        replies.push(reply);
        localStorage.setItem(this.STORAGE_KEYS.REPLIES, JSON.stringify(replies));
    }

    /**
     * Get replies for a specific ticket
     */
    private async getTicketReplies(ticketId: string): Promise<TicketReply[]> {
        const replies = this.getStoredReplies();
        return replies
            .filter(reply => reply.ticketId === ticketId)
            .sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime());
    }

    /**
     * Get attachments for a specific ticket
     */
    private async getTicketAttachments(ticketId: string): Promise<TicketAttachment[]> {
        const attachments = this.getStoredAttachments();
        return attachments.filter(attachment => 
            attachment.id.startsWith(ticketId) // Assuming attachment IDs are prefixed with ticket ID
        );
    }

    /**
     * Get history entries for a specific ticket
     */
    private async getTicketHistory(ticketId: string): Promise<TicketHistoryEntry[]> {
        const history = this.getStoredHistory();
        return history
            .filter(entry => entry.ticketId === ticketId)
            .sort((a, b) => a.performedAt.getTime() - b.performedAt.getTime());
    }

    /**
     * Get members for a specific ticket
     */
    private async getTicketMembers(ticket: Ticket): Promise<TicketMember[]> {
        const members: TicketMember[] = [];
        
        // Add ticket creator
        try {
            const currentUser = this.getCurrentUser();
            if (ticket.userId === currentUser.id) {
                members.push({
                    userId: currentUser.id,
                    username: currentUser.username,
                    displayName: currentUser.username,
                    avatar: currentUser.avatar,
                    isStaff: false,
                    joinedAt: ticket.createdAt
                });
            }
        } catch (error) {
            // If we can't get current user info, add a placeholder
            members.push({
                userId: ticket.userId,
                username: 'Unknown User',
                displayName: 'Unknown User',
                avatar: undefined,
                isStaff: false,
                joinedAt: ticket.createdAt
            });
        }

        // Add other participants (staff members would be added here in a real implementation)
        // For now, we only have the ticket creator

        return members;
    }

    /**
     * Add a history entry
     */
    private async addHistoryEntry(
        ticketId: string, 
        action: string, 
        description: string, 
        performedBy: string,
        metadata?: Record<string, any>
    ): Promise<void> {
        const history = this.getStoredHistory();
        const entry: TicketHistoryEntry = {
            id: `HST-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`.toUpperCase(),
            ticketId,
            action,
            description,
            performedBy,
            performedAt: new Date(),
            metadata
        };

        history.push(entry);
        localStorage.setItem(this.STORAGE_KEYS.HISTORY, JSON.stringify(history));
    }
}