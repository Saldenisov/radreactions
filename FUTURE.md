# FUTURE: RadReactions Platform Vision and SEO/Migration Plan

Status: Draft
Owner: Sergey A. Denisov
Last updated: 2025-08-27

---

## Vision and positioning
- One-liner: "Modern radiation chemistry platform — validated Buxton kinetics, digitized datasets, and tools like SK-ana."
- Primary goals:
  - Publish Digitized Buxton dataset with clear citation and versioning
  - Provide Buxton validation pages with reproducible notebooks
  - Host tools (e.g., SK-ana) with quickstart docs and examples
  - Improve discoverability with robust SEO and structured data

## Information architecture (IA)
- Top-level navigation:
  - Home
  - About
  - Tools (SK-ana)
  - Datasets (Digitized Buxton)
  - Validation (Buxton validation)
  - Docs
  - Publications/Blog
  - How to Cite
  - License
  - Contact
- Each page must have unique, descriptive titles and meta descriptions.

## Migration and domain strategy
- Choose a canonical domain: e.g., `radreactions.org` or `radreactions.academy`.
- Implement 301 redirects from all `elyse-platform.academy` URLs to the new domain.
- Keep old domain online with redirects for 6–12 months (minimum).
- Update internal links to absolute canonical URLs.

### Example 301 redirects
If using Netlify/Vercel-like hosting (_redirects file):

```text
# _redirects
https://elyse-platform.academy/* https://radreactions.org/:splat 301!
/blog/* /publications/:splat 301
```

If using Nginx:

```nginx
server {
  listen 443 ssl;
  server_name elyse-platform.academy www.elyse-platform.academy;
  return 301 https://radreactions.org$request_uri;
}
```

## Technical SEO essentials
- robots.txt, sitemap.xml, canonical tags on every page
- HTTPS, consistent host (www vs non-www), HSTS
- Open Graph + Twitter card metadata for rich link previews

robots.txt:

```text
User-agent: *
Disallow:
Sitemap: https://radreactions.org/sitemap.xml
```

Open Graph/Twitter example:

```html
<meta property="og:type" content="website" />
<meta property="og:site_name" content="RadReactions" />
<meta property="og:title" content="Modern Radiation Chemistry Platform" />
<meta property="og:description" content="Validated Buxton kinetics, digitized datasets, and tools like SK-ana." />
<meta property="og:url" content="https://radreactions.org/" />
<meta property="og:image" content="https://radreactions.org/og-image.jpg" />
<meta name="twitter:card" content="summary_large_image" />
```

## Structured data (JSON-LD)
Add schema.org JSON-LD to pages to appear in Google Dataset Search and enhance software/article results.

Organization:

```json
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "RadReactions",
  "url": "https://radreactions.org",
  "sameAs": [
    "https://scholar.google.com/citations?user=YOUR_ID",
    "https://github.com/YOUR_ORG"
  ]
}
```

Dataset (Digitized Buxton):

```json
{
  "@context": "https://schema.org",
  "@type": "Dataset",
  "name": "Digitized Buxton Reaction Set for Water Radiolysis",
  "description": "Digitized kinetic scheme and parameters from Buxton et al. for aqueous radiolysis; validated and versioned for computational use.",
  "url": "https://radreactions.org/datasets/buxton",
  "sameAs": "https://doi.org/10.xxxx/your-buxton-doi",
  "creator": {
    "@type": "Organization",
    "name": "RadReactions"
  },
  "citation": "Buxton et al., Journal of Physical and Chemical Reference Data (year)...",
  "license": "https://creativecommons.org/licenses/by/4.0/",
  "distribution": [
    {
      "@type": "DataDownload",
      "encodingFormat": "application/json",
      "contentUrl": "https://radreactions.org/data/buxton/buxton.json"
    }
  ],
  "keywords": ["radiation chemistry", "radiolysis", "water", "Buxton", "kinetics"]
}
```

Software (SK-ana):

```json
{
  "@context": "https://schema.org",
  "@type": "SoftwareSourceCode",
  "name": "SK-ana",
  "codeRepository": "https://github.com/YOUR_ORG/SK-Ana",
  "programmingLanguage": "Python",
  "applicationCategory": "ScientificSoftware",
  "url": "https://radreactions.org/tools/sk-ana",
  "license": "https://opensource.org/licenses/MIT",
  "keywords": ["kinetic analysis", "radiation chemistry", "time-resolved spectra"]
}
```

Article example (for Publications/Blog):

```json
{
  "@context": "https://schema.org",
  "@type": "ScholarlyArticle",
  "headline": "Quasi-Free Electron-Mediated Radiation Sensitization by C5-Halopyrimidines",
  "author": [{"@type": "Person", "name": "Sergey A. Denisov"}],
  "datePublished": "2021-09-02",
  "isPartOf": {"@type": "Blog", "name": "RadReactions Blog"},
  "url": "https://radreactions.org/publications/quasi-free-electron-sensitization"
}
```

## Performance and UX (Core Web Vitals)
- Optimize images (WebP/AVIF); lazy-load non-critical media
- Minify/treeshake CSS/JS; defer non-critical JS
- Use CDN/static hosting (Netlify, Vercel, Cloudflare Pages, GitHub Pages)
- Accessibility: alt text, headings structure, labels

## Indexing and webmaster tools
- Verify both domains in Google Search Console and Bing Webmaster Tools
- Submit sitemap: `https://radreactions.org/sitemap.xml`
- Use Google "Change of Address" after 301s are live
- Provide RSS/Atom feed for Publications/Blog

## Content plan to attract links and queries
- Digitized Buxton landing: download links, API/spec, changelog, citation
- Buxton validation: methods, figures, reproducible notebooks
- SK-ana docs: quickstart, real spectra examples, API reference
- How to Cite and LICENSE pages
- Methods notes and benchmarks; cross-post to arXiv/institutional pages with backlinks

## Backlinks and community signals
- Link from CNRS/Université Paris-Saclay/ELYSE pages
- Add site links from GitHub repos (SK-Ana, radreactions); add repo topics and CITATION.cff
- Add URL to Google Scholar, ORCID, ResearchGate
- Announce releases on relevant mailing lists and social platforms

## Analytics and privacy
- Add privacy-friendly analytics (Plausible or Matomo) to track traffic and search queries

## Monitoring
- Uptime monitoring for the site
- Weekly checks for Core Web Vitals and coverage in Search Console

## Implementation next steps in this repository
- Add `robots.txt`, `sitemap.xml` scaffolding
- Add Open Graph/Twitter meta includes
- Add JSON-LD includes for Organization, Dataset (Buxton), and Software (SK-ana)
- Prepare redirects config (host-dependent)
- Scaffold basic site structure and placeholder pages for: Tools, Datasets, Validation, Docs, Publications, How to Cite, License, Contact

## Open questions
- Canonical domain choice (radreactions.org vs radreactions.academy)
- Hosting provider (Netlify, Vercel, Cloudflare Pages, GitHub Pages, other)
- Preserve current blog/post URLs vs reorganize under `/publications`
- Proceed to scaffold SEO files and JSON-LD in this repo now?
