# Fuse.gg Website Deployment Guide

## Your Website is Ready for .io Domain!

### Quick Start - Deploy to Netlify (Recommended)

1. **Go to Netlify**: https://www.netlify.com
2. **Sign up** for free account
3. **Drag and drop** your `web` folder to Netlify
4. **Get your domain**: Register `fuse.gg` or similar at:
   - Namecheap: https://www.namecheap.com
   - Cloudflare: https://www.cloudflare.com
5. **Connect domain** in Netlify settings → Domain Management

### Domain Suggestions

Available .io domains you might like:
- `fusegg.io`
- `fuse-gg.io`
- `fusegaming.io`
- `medusabypass.io`

### Step-by-Step Netlify Deployment

#### 1. Prepare Your Files
Your website is in the `web` folder. This contains:
- `index.html` - Your main website
- `images/` folder - All your images

#### 2. Deploy to Netlify
```
1. Visit https://app.netlify.com/drop
2. Drag the entire 'web' folder onto the page
3. Wait for deployment (takes ~30 seconds)
4. You'll get a URL like: https://random-name-123.netlify.app
```

#### 3. Add Custom Domain
```
1. In Netlify dashboard, click "Domain settings"
2. Click "Add custom domain"
3. Enter your .io domain (e.g., fusegg.io)
4. Netlify will provide DNS records
```

#### 4. Configure DNS at Your Domain Registrar
Add these records at your domain provider:

**For Netlify:**
```
Type: A
Name: @
Value: 75.2.60.5

Type: CNAME  
Name: www
Value: [your-site].netlify.app
```

#### 5. Enable HTTPS
Netlify automatically provides free SSL certificate (HTTPS)

### Alternative: GitHub Pages

1. Create GitHub account
2. Create repository named `username.github.io`
3. Upload files from `web` folder
4. Go to Settings → Pages
5. Add custom domain

### Alternative: Cloudflare Pages

1. Sign up at https://pages.cloudflare.com
2. Connect your GitHub repository
3. Deploy automatically
4. Add custom domain (free SSL included)

### DNS Configuration

Once you have hosting, update DNS at your domain registrar:

**A Record:**
```
Host: @
Points to: [Your hosting IP]
TTL: Automatic
```

**CNAME Record:**
```
Host: www
Points to: [Your hosting domain]
TTL: Automatic
```

### SSL Certificate (HTTPS)

All recommended hosts provide free SSL:
- Netlify: Automatic
- Cloudflare Pages: Automatic  
- GitHub Pages: Automatic

### Files to Update Before Deployment

1. **Update Payment Details** in `index.html`:
   - Line ~1760: PayPal username
   - Line ~1770: Crypto wallet addresses
   - Line ~1775: Conversion rates

2. **Add Your Images** to `images/` folder:
   - `fuse-logo.png` - Your logo
   - `product-pro.jpg` - Product image
   - `shield-icon.png` - Shield icon
   - `microscope-icon.png` - Scanner icon
   - `hero-bg.jpg` - Background image (optional)

3. **Update Discord Link** in `index.html`:
   - Line ~1285: Replace with your Discord invite

### Testing Before Deployment

1. Open `index.html` in your browser
2. Test all navigation tabs
3. Test checkout process
4. Verify all images load
5. Test on mobile device

### Post-Deployment Checklist

- [ ] Domain is live and accessible
- [ ] HTTPS is working (green padlock)
- [ ] All images are loading
- [ ] Payment methods are configured
- [ ] Discord link works
- [ ] Mobile responsive design works
- [ ] All tabs navigate correctly

### Cost Breakdown

**Free Option:**
- Hosting: $0 (Netlify/Cloudflare Pages)
- Domain: ~$30-40/year (.io domain)
- SSL: $0 (included)
**Total: ~$30-40/year**

**Paid Option:**
- Hosting: $5/month (DigitalOcean)
- Domain: ~$30-40/year
- SSL: $0 (Let's Encrypt)
**Total: ~$90-100/year**

### Support

If you need help:
1. Netlify Docs: https://docs.netlify.com
2. Cloudflare Docs: https://developers.cloudflare.com/pages
3. GitHub Pages: https://docs.github.com/pages

### Your Website Features

✅ Responsive design (mobile-friendly)
✅ Purple particle background
✅ Product showcase with status
✅ Shopping cart system
✅ Checkout with multiple payment methods
✅ PayPal integration
✅ Crypto payment modals (BTC, LTC, SOL)
✅ Scanner status dashboard
✅ Custom icons support
✅ Professional navigation

### Next Steps

1. **Register your .io domain** (recommended: fusegg.io)
2. **Deploy to Netlify** (drag and drop)
3. **Connect your domain** (follow Netlify instructions)
4. **Add your payment details** (PayPal, crypto addresses)
5. **Upload your custom images**
6. **Test everything**
7. **Go live!**

Your website is production-ready and optimized for a .io domain!
