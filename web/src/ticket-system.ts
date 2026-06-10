// Main TicketSystem class - Controller for ticket functionality

import { 
    Ticket, 
    TicketDetails, 
    CreateTicketRequest, 
    TicketStatus, 
    TicketFilters,
    TicketCategory 
} from './types';
import { TicketAPI } from './ticket-api';

/**
 * Main controller class for ticket functionality
 * Manages UI state and coordinates between API and UI components
 */
export class TicketSystem {
    private currentView: 'main' | 'detail' = 'main';
    private currentTicketId: string | null = null;
    private isCreateModalOpen: boolean = false;
    private tickets: Ticket[] = [];
    private filteredTickets: Ticket[] = [];
    private ticketAPI: TicketAPI;

    constructor() {
        this.ticketAPI = new TicketAPI();
        this.initialize();
    }

    /**
     * Initialize ticket system UI and event handlers
     */
    public initialize(): void {
        this.setupEventListeners();
        this.loadInitialData();
    }

    /**
     * Navigate to tickets page from dashboard
     */
    public navigateToTickets(): void {
        // Check authentication first
        if (!this.isUserAuthenticated()) {
            this.redirectToAuthentication();
            return;
        }

        // Navigate to tickets page
        window.location.href = '/tickets.html';
    }

    /**
     * Show main tickets page with table view
     */
    public showMainTicketsPage(): void {
        this.currentView = 'main';
        this.currentTicketId = null;
        this.renderMainTicketsView();
    }

    /**
     * Show individual ticket detail view
     * @param ticketId - ID of the ticket to display
     */
    public async showIndividualTicket(ticketId: string): Promise<void> {
        try {
            this.currentView = 'detail';
            this.currentTicketId = ticketId;
            
            const ticketDetails = await this.loadTicketDetails(ticketId);
            this.renderIndividualTicketView(ticketDetails);
        } catch (error) {
            console.error('Error loading ticket details:', error);
            this.showErrorMessage('Failed to load ticket details. Please try again.');
            this.showMainTicketsPage();
        }
    }

    /**
     * Create a new ticket
     * @param ticketData - Data for the new ticket
     * @returns Promise resolving to the created ticket
     */
    public async createTicket(ticketData: CreateTicketRequest): Promise<Ticket> {
        try {
            // Create ticket using API
            const newTicket = await this.ticketAPI.createTicket(ticketData);

            // Update local tickets array
            this.tickets.unshift(newTicket);
            this.filteredTickets = [...this.tickets];

            // Close modal and refresh view
            this.hideCreateTicketModal();
            this.showSuccessMessage(`Ticket #${newTicket.id} created successfully!`);
            this.refreshTicketsTable();

            return newTicket;
        } catch (error) {
            console.error('Error creating ticket:', error);
            this.showErrorMessage('Failed to create ticket. Please try again.');
            throw error;
        }
    }

    /**
     * Load all tickets for the current user
     * @returns Promise resolving to array of tickets
     */
    public async loadTickets(): Promise<Ticket[]> {
        try {
            const userId = this.getCurrentUserId();
            const tickets = await this.ticketAPI.getUserTickets(userId);
            
            this.tickets = tickets;
            this.filteredTickets = [...tickets];
            
            return tickets;
        } catch (error) {
            console.error('Error loading tickets:', error);
            this.showErrorMessage('Failed to load tickets. Please refresh the page.');
            return [];
        }
    }

    /**
     * Load detailed information for a specific ticket
     * @param ticketId - ID of the ticket to load
     * @returns Promise resolving to ticket details
     */
    public async loadTicketDetails(ticketId: string): Promise<TicketDetails> {
        try {
            const ticketDetails = await this.ticketAPI.getTicketDetails(ticketId);
            return ticketDetails;
        } catch (error) {
            console.error('Error loading ticket details:', error);
            throw new Error('Failed to load ticket details');
        }
    }

    /**
     * Update ticket status
     * @param ticketId - ID of the ticket to update
     * @param status - New status for the ticket
     */
    public async updateTicketStatus(ticketId: string, status: TicketStatus): Promise<void> {
        try {
            await this.ticketAPI.updateTicket(ticketId, { status, updatedAt: new Date() });
            
            // Update local tickets array
            const ticketIndex = this.tickets.findIndex(t => t.id === ticketId);
            if (ticketIndex !== -1) {
                this.tickets[ticketIndex].status = status;
                this.tickets[ticketIndex].updatedAt = new Date();
            }

            this.refreshCurrentView();
            this.showSuccessMessage('Ticket status updated successfully');
        } catch (error) {
            console.error('Error updating ticket status:', error);
            this.showErrorMessage('Failed to update ticket status. Please try again.');
        }
    }

    /**
     * Add a reply to a ticket
     * @param ticketId - ID of the ticket to reply to
     * @param message - Reply message content
     */
    public async addReply(ticketId: string, message: string): Promise<void> {
        try {
            const userId = this.getCurrentUserId();
            const reply = {
                ticketId: ticketId,
                authorId: userId,
                authorName: this.getCurrentUserName(),
                authorAvatar: this.getCurrentUserAvatar(),
                message: message.trim(),
                isStaff: false,
                attachments: []
            };

            await this.ticketAPI.addReply(ticketId, reply);

            // Update local ticket data
            const ticketIndex = this.tickets.findIndex(t => t.id === ticketId);
            if (ticketIndex !== -1) {
                this.tickets[ticketIndex].lastReplyAt = new Date();
                this.tickets[ticketIndex].messageCount += 1;
                this.tickets[ticketIndex].updatedAt = new Date();
            }

            this.refreshCurrentView();
            this.showSuccessMessage('Reply added successfully');
        } catch (error) {
            console.error('Error adding reply:', error);
            this.showErrorMessage('Failed to add reply. Please try again.');
        }
    }

    /**
     * Search tickets by query string
     * @param query - Search query
     * @returns Array of matching tickets
     */
    public async searchTickets(query: string): Promise<Ticket[]> {
        try {
            const userId = this.getCurrentUserId();
            const searchResults = await this.ticketAPI.searchTickets(userId, query);
            
            this.filteredTickets = searchResults;
            this.refreshTicketsTable();
            return this.filteredTickets;
        } catch (error) {
            console.error('Error searching tickets:', error);
            this.showErrorMessage('Failed to search tickets. Please try again.');
            return [];
        }
    }

    /**
     * Filter tickets by various criteria
     * @param filters - Filter criteria
     * @returns Array of filtered tickets
     */
    public async filterTickets(filters: TicketFilters): Promise<Ticket[]> {
        try {
            const userId = this.getCurrentUserId();
            let filtered = [...this.tickets];

            if (filters.status) {
                filtered = await this.ticketAPI.getTicketsByStatus(userId, filters.status);
            } else if (filters.category) {
                filtered = await this.ticketAPI.getTicketsByCategory(userId, filters.category);
            } else {
                // Apply other filters locally
                if (filters.dateFrom) {
                    filtered = filtered.filter(ticket => ticket.createdAt >= filters.dateFrom!);
                }

                if (filters.dateTo) {
                    filtered = filtered.filter(ticket => ticket.createdAt <= filters.dateTo!);
                }
            }

            this.filteredTickets = filtered;
            this.refreshTicketsTable();
            return this.filteredTickets;
        } catch (error) {
            console.error('Error filtering tickets:', error);
            this.showErrorMessage('Failed to filter tickets. Please try again.');
            return [];
        }
    }

    /**
     * Show create ticket modal
     */
    public showCreateTicketModal(): void {
        this.isCreateModalOpen = true;
        this.renderCreateTicketModal();
    }

    /**
     * Hide create ticket modal
     */
    public hideCreateTicketModal(): void {
        this.isCreateModalOpen = false;
        this.removeCreateTicketModal();
    }

    /**
     * Navigate back to main tickets page from detail view
     */
    public navigateBack(): void {
        if (this.currentView === 'detail') {
            this.showMainTicketsPage();
        }
    }

    // Private helper methods

    private setupEventListeners(): void {
        // Expose methods globally for onclick handlers
        (window as any).ticketSystem = this;
        (window as any).navigateToTickets = () => this.navigateToTickets();
        (window as any).showCreateTicketModal = () => this.showCreateTicketModal();
        (window as any).hideCreateTicketModal = () => this.hideCreateTicketModal();
        (window as any).showIndividualTicket = (ticketId: string) => this.showIndividualTicket(ticketId);
        (window as any).navigateBack = () => this.navigateBack();
    }

    private async loadInitialData(): Promise<void> {
        if (this.isUserAuthenticated()) {
            await this.loadTickets();
        }
    }

    private isUserAuthenticated(): boolean {
        // Check if user is authenticated via Discord
        const discordUser = localStorage.getItem('discord_user');
        return !!discordUser;
    }

    private getCurrentUserId(): string {
        const discordUser = localStorage.getItem('discord_user');
        if (!discordUser) {
            throw new Error('User not authenticated');
        }
        return JSON.parse(discordUser).id;
    }

    private getCurrentUserName(): string {
        const discordUser = localStorage.getItem('discord_user');
        if (!discordUser) {
            return 'Unknown User';
        }
        const user = JSON.parse(discordUser);
        return user.username || user.global_name || 'Unknown User';
    }

    private getCurrentUserAvatar(): string | undefined {
        const discordUser = localStorage.getItem('discord_user');
        if (!discordUser) {
            return undefined;
        }
        const user = JSON.parse(discordUser);
        return user.avatar ? `https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png` : undefined;
    }

    private redirectToAuthentication(): void {
        // Redirect to Discord OAuth or login page
        window.location.href = '/dashboard.html';
    }

    private generateTicketId(): string {
        // Generate UUID-like ticket ID
        return 'ticket_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    private generateReplyId(): string {
        return 'reply_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    // UI rendering methods (to be implemented by TicketUI component)
    private renderMainTicketsView(): void {
        // This will be implemented when TicketUI component is created
        console.log('Rendering main tickets view');
    }

    private renderIndividualTicketView(ticketDetails: TicketDetails): void {
        // This will be implemented when TicketUI component is created
        console.log('Rendering individual ticket view for:', ticketDetails.id);
    }

    private renderCreateTicketModal(): void {
        // This will be implemented when TicketUI component is created
        console.log('Rendering create ticket modal');
    }

    private removeCreateTicketModal(): void {
        // This will be implemented when TicketUI component is created
        console.log('Removing create ticket modal');
    }

    private refreshTicketsTable(): void {
        // This will be implemented when TicketUI component is created
        console.log('Refreshing tickets table');
    }

    private refreshCurrentView(): void {
        if (this.currentView === 'main') {
            this.refreshTicketsTable();
        } else if (this.currentView === 'detail' && this.currentTicketId) {
            this.showIndividualTicket(this.currentTicketId);
        }
    }

    private showSuccessMessage(message: string): void {
        // This will be implemented when TicketUI component is created
        console.log('Success:', message);
    }

    private showErrorMessage(message: string): void {
        // This will be implemented when TicketUI component is created
        console.error('Error:', message);
    }

    // Data persistence methods (handled by TicketAPI)
    // These methods are kept for backward compatibility but delegate to TicketAPI
    
    /**
     * @deprecated Use TicketAPI directly instead
     */
    public async backupTicketData(): Promise<void> {
        return this.ticketAPI.backupTicketData();
    }

    /**
     * @deprecated Use TicketAPI directly instead
     */
    public async restoreTicketData(): Promise<void> {
        return this.ticketAPI.restoreTicketData();
    }
}