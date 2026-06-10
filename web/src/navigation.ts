// Navigation system for tab switching

export class Navigation {
    private navLinks: NodeListOf<HTMLAnchorElement>;
    private sections: {
        store: HTMLElement | null;
        hero: HTMLElement | null;
        status: HTMLElement | null;
        tos: HTMLElement | null;
        payment: HTMLElement | null;
    };

    constructor() {
        this.navLinks = document.querySelectorAll('.nav-links a');
        this.sections = {
            store: document.getElementById('storeSection'),
            hero: document.querySelector('.hero'),
            status: document.querySelector('.status-section'),
            tos: document.getElementById('tosSection'),
            payment: document.querySelector('.payment-section')
        };
    }

    public initialize(): void {
        this.navLinks.forEach(link => {
            link.addEventListener('click', (e) => this.handleNavClick(e, link));
        });
    }

    private handleNavClick(e: Event, link: HTMLAnchorElement): void {
        if (link.getAttribute('target') === '_blank') {
            return;
        }
        
        e.preventDefault();
        this.navLinks.forEach(l => l.classList.remove('active'));
        link.classList.add('active');
        
        this.sections.payment?.classList.remove('show');
        
        const target = link.getAttribute('href')?.substring(1);
        this.showSection(target || 'home');
    }

    private showSection(target: string): void {
        const { store, hero, status, tos } = this.sections;

        if (target === 'store') {
            store?.classList.add('active');
            if (hero) hero.style.display = 'none';
            if (status) status.style.display = 'none';
            tos?.classList.remove('active');
        } else if (target === 'home') {
            store?.classList.remove('active');
            if (hero) hero.style.display = 'block';
            if (status) status.style.display = 'block';
            tos?.classList.remove('active');
        } else if (target === 'tos') {
            store?.classList.remove('active');
            if (hero) hero.style.display = 'none';
            if (status) status.style.display = 'none';
            tos?.classList.add('active');
        } else {
            store?.classList.remove('active');
            if (hero) hero.style.display = 'none';
            if (status) status.style.display = 'none';
            tos?.classList.remove('active');
        }
    }

    public activateHome(): void {
        this.navLinks.forEach(l => l.classList.remove('active'));
        const homeLink = document.querySelector('.nav-links a[href="#home"]');
        homeLink?.classList.add('active');
    }
}
