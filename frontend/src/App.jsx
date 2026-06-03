import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import DashboardPage from './pages/DashboardPage'
import QueryPage from './pages/QueryPage'

function App() {
  return (
    <BrowserRouter>
      <nav className="navbar">
        <span className="navbar-brand">Logistics Analytics</span>
        <NavLink to="/" end className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
          Dashboard
        </NavLink>
        <NavLink to="/query" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
          AI Query
        </NavLink>
      </nav>
      <main className="main-content">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/query" element={<QueryPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}

export default App
