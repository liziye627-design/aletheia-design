const enableNewUi = String(import.meta.env.VITE_NEW_PROGRAM_UI ?? '1').trim() !== '0'

async function bootstrap() {
  const legacyRoot = document.getElementById('legacy-app')
  const reactRoot = document.getElementById('root')
  const legacyStyles = document.getElementById('legacy-styles')

  if (enableNewUi) {
    if (legacyRoot) legacyRoot.style.display = 'none'
    if (legacyStyles) legacyStyles.setAttribute('disabled', 'true')
    if (reactRoot) reactRoot.style.display = 'block'
    await import('./main.tsx')
    return
  }

  if (reactRoot) reactRoot.style.display = 'none'
  if (legacyRoot) legacyRoot.style.display = 'block'
  if (legacyStyles) legacyStyles.removeAttribute('disabled')
  await import('./main.js')
}

void bootstrap()
