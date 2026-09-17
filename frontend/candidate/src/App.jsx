import { BrowserRouter, Route, Routes } from 'react-router-dom';
import ApplyPage from './pages/ApplyPage';
import InterviewFlow from './pages/InterviewFlow';
import './App.css';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ApplyPage />} />
        <Route path="/apply" element={<ApplyPage />} />
        <Route path="/apply/:jobId" element={<ApplyPage />} />
        <Route path="/interview" element={<InterviewFlow />} />
        <Route path="/interview/:token" element={<InterviewFlow />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
