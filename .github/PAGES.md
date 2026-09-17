# GitHub Pages — ZASI

> Repository: cvsz/zasi
> URL: https://cvsz.github.io/zasi

## Configuration

GitHub Pages is configured via .github/workflows/pages.yml:
- Source branch: gh-pages (auto-created by Pages workflow)
- Build: Vite static export from web/ directory
- Published to: https://cvsz.github.io/zasi

## How Pages Works

web/ (source) -> Vite build -> dist/ -> gh-pages branch -> https://cvsz.github.io/zasi

## Managing Pages

### Enable/Disable Pages
1. Settings -> Pages
2. Select source branch and folder
3. Save

### Custom Domain
1. Add CNAME file to gh-pages branch root
2. Settings -> Pages -> Custom domain
3. Configure DNS: CNAME your-domain.com -> cvsz.github.io
4. Enable "Enforce HTTPS"

### Troubleshooting

| Issue | Solution |
|---|---|
| Page not updating | Check Pages workflow run in Actions |
| 404 on refresh | SPA routing issue |
| Custom domain not working | Check DNS CNAME and GitHub Pages settings |
| Build failing | Check Pages workflow logs |

## SPA Configuration

Since ZASI web is a single-page application, add a _redirects file to web/dist/:

/*    /index.html   200

## Preview Deployments

For preview deployments per PR:
- Use separate workflow that builds web/ and deploys to temporary Pages site
- Store preview URL as PR check annotation or comment
- Clean up after PR merge/close
