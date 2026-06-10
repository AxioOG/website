// Particle animation system for constellation-style background

import { Particle } from './types';

export class ParticleSystem {
    private particlesContainer: HTMLElement;
    private particles: Particle[] = [];
    private readonly particleCount = 120;
    private readonly movingCount = 30;

    constructor(containerId: string) {
        const container = document.getElementById(containerId);
        if (!container) {
            throw new Error(`Container with id "${containerId}" not found`);
        }
        this.particlesContainer = container;
    }

    public initialize(): void {
        this.createStaticParticles();
        this.createConnections();
        this.createMovingParticles();
    }

    private createStaticParticles(): void {
        for (let i = 0; i < this.particleCount; i++) {
            const particle = document.createElement('div');
            particle.className = 'particle';
            
            const sizeType = Math.random();
            let size: number;
            if (sizeType < 0.15) {
                size = 8;
                particle.classList.add('large');
            } else if (sizeType < 0.5) {
                size = 5;
            } else {
                size = 3;
                particle.classList.add('small');
            }
            
            const animationType = Math.random();
            if (animationType < 0.3) {
                particle.classList.add('fast');
            } else if (animationType < 0.6) {
                particle.classList.add('slow');
            }
            
            particle.style.width = size + 'px';
            particle.style.height = size + 'px';
            
            const x = Math.random() * (window.innerWidth - 100) + 50;
            const y = Math.random() * (window.innerHeight - 100) + 50;
            particle.style.left = x + 'px';
            particle.style.top = y + 'px';
            particle.style.animationDelay = Math.random() * 5 + 's';
            
            this.particlesContainer.appendChild(particle);
            this.particles.push({ element: particle, x, y, originalX: x, originalY: y });
        }
    }

    private createConnections(): void {
        for (let i = 0; i < this.particles.length; i++) {
            for (let j = i + 1; j < this.particles.length; j++) {
                const particle1 = this.particles[i];
                const particle2 = this.particles[j];
                
                const distance = Math.sqrt(
                    Math.pow(particle2.x - particle1.x, 2) + 
                    Math.pow(particle2.y - particle1.y, 2)
                );
                
                if (distance < 100) {
                    const line = document.createElement('div');
                    line.className = 'connection-line';
                    
                    const angle = Math.atan2(particle2.y - particle1.y, particle2.x - particle1.x);
                    
                    line.style.left = particle1.x + 'px';
                    line.style.top = particle1.y + 'px';
                    line.style.width = distance + 'px';
                    line.style.transform = `rotate(${angle}rad)`;
                    line.style.animationDelay = Math.random() * 6 + 's';
                    
                    this.particlesContainer.appendChild(line);
                }
            }
        }
    }

    private createMovingParticles(): void {
        for (let i = 0; i < this.movingCount; i++) {
            const particle = document.createElement('div');
            particle.className = 'particle moving-particle';
            
            const size = Math.random() * 4 + 2;
            particle.style.width = size + 'px';
            particle.style.height = size + 'px';
            
            const edge = Math.floor(Math.random() * 4);
            let startX: number, startY: number;
            
            switch(edge) {
                case 0:
                    startX = Math.random() * window.innerWidth;
                    startY = -10;
                    break;
                case 1:
                    startX = window.innerWidth + 10;
                    startY = Math.random() * window.innerHeight;
                    break;
                case 2:
                    startX = Math.random() * window.innerWidth;
                    startY = window.innerHeight + 10;
                    break;
                case 3:
                default:
                    startX = -10;
                    startY = Math.random() * window.innerHeight;
                    break;
            }
            
            particle.style.left = startX + 'px';
            particle.style.top = startY + 'px';
            particle.style.animationDelay = Math.random() * 8 + 's';
            
            this.animateMovingParticle(particle, startX, startY);
            this.particlesContainer.appendChild(particle);
        }
    }

    private animateMovingParticle(particle: HTMLElement, startX: number, startY: number): void {
        const duration = Math.random() * 15000 + 10000;
        const endX = Math.random() * window.innerWidth;
        const endY = Math.random() * window.innerHeight;
        
        particle.animate([
            { transform: `translate(0px, 0px)`, opacity: 0 },
            { transform: `translate(${(endX - startX) * 0.1}px, ${(endY - startY) * 0.1}px)`, opacity: 1, offset: 0.1 },
            { transform: `translate(${(endX - startX) * 0.9}px, ${(endY - startY) * 0.9}px)`, opacity: 1, offset: 0.9 },
            { transform: `translate(${endX - startX}px, ${endY - startY}px)`, opacity: 0 }
        ], {
            duration,
            easing: 'ease-in-out',
            iterations: Infinity
        });
    }

    public clear(): void {
        this.particlesContainer.innerHTML = '';
        this.particles = [];
    }

    public recreate(): void {
        this.clear();
        setTimeout(() => this.initialize(), 100);
    }
}
