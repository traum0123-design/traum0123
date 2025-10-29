import { defineConfig } from 'vite'
import { resolve } from 'path'

// Build manifest compatible with resolve_static mapping
export default defineConfig({
  root: resolve(__dirname, '..'),
  build: {
    manifest: true,
    outDir: resolve(__dirname, '../payroll_portal/static/dist'),
    emptyOutDir: false,
    rollupOptions: {
      input: {
        'app.js': resolve(__dirname, '../payroll_portal/static/app.js'),
        'init_csrf.js': resolve(__dirname, '../payroll_portal/static/init_csrf.js'),
        'i18n.js': resolve(__dirname, '../payroll_portal/static/i18n.js'),
        'portal_home.js': resolve(__dirname, '../payroll_portal/static/portal_home.js'),
        'admin_withholding.js': resolve(__dirname, '../payroll_portal/static/admin_withholding.js'),
        'runtime.js': resolve(__dirname, '../payroll_portal/static/runtime.js'),
        'styles.css': resolve(__dirname, '../payroll_portal/static/styles.css'),
        'payroll/calc.js': resolve(__dirname, '../payroll_portal/static/payroll/calc.js'),
        'payroll/dom.js': resolve(__dirname, '../payroll_portal/static/payroll/dom.js'),
        'payroll/state.js': resolve(__dirname, '../payroll_portal/static/payroll/state.js'),
        'payroll/ui.js': resolve(__dirname, '../payroll_portal/static/payroll/ui.js'),
        'payroll/utils.js': resolve(__dirname, '../payroll_portal/static/payroll/utils.js')
      }
    }
  }
})

