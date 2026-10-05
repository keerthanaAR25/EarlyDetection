export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: { extend: {
    colors: {
      bg: '#0b0e14', panel: '#131722', border: '#232838',
      text: '#e6e9f0', muted: '#8b93a7',
      critical: '#ef4444', high: '#f97316', moderate: '#eab308', low: '#22c55e',
      accent: '#3b82f6',
    }
  } },
  plugins: [],
}
