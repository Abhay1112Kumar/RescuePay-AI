// Development verification entry only; not linked from the product UI.
import { createRoot } from 'react-dom/client'
import { PaymentExplanation } from './components/PaymentExplanation'
import './components/SandboxCheckout.css'
createRoot(document.getElementById('root')!).render(<main style={{maxWidth:1000,margin:'24px auto',padding:20,fontFamily:'system-ui'}}>
<h1>Synthetic explanation verification</h1><p><strong>SYNTHETIC TEST RECORDS AND MOCKED GEMINI RESPONSES ONLY. No real AI or PayPal calls.</strong></p>
<h2>Unconfigured provider</h2><PaymentExplanation orderId="TESTUNCERTAIN001" />
<h2>Valid mocked model selection</h2><PaymentExplanation orderId="TESTVALIDMODEL01" />
<h2>Invalid mocked claim rejected</h2><PaymentExplanation orderId="TESTINVALIDMODEL1" />
</main>)
