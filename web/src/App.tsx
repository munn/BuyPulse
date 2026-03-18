import { ConfigProvider, Spin } from 'antd'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AdminLayout from './layouts/AdminLayout'
import { useAuth } from './hooks/useAuth'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Products from './pages/Products'
import Crawler from './pages/Crawler'
import Imports from './pages/Imports'
import Audit from './pages/Audit'

export default function App() {
  const { user, loading, login, logout } = useAuth()

  if (loading) {
    return (
      <Spin
        size="large"
        style={{
          display: 'flex',
          justifyContent: 'center',
          marginTop: '40vh',
        }}
      />
    )
  }

  return (
    <ConfigProvider>
      <BrowserRouter>
        <Routes>
          <Route
            path="/login"
            element={
              user ? <Navigate to="/dashboard" /> : <Login onLogin={login} />
            }
          />
          {user ? (
            <Route
              element={
                <AdminLayout username={user.username} onLogout={logout} />
              }
            >
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/products" element={<Products />} />
              <Route path="/crawler" element={<Crawler />} />
              <Route path="/imports" element={<Imports />} />
              <Route path="/audit" element={<Audit />} />
              <Route path="*" element={<Navigate to="/dashboard" />} />
            </Route>
          ) : (
            <Route path="*" element={<Navigate to="/login" />} />
          )}
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}
