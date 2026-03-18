import {
  AuditOutlined,
  CloudUploadOutlined,
  DashboardOutlined,
  LogoutOutlined,
  ShoppingOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { Layout, Menu, Typography } from 'antd'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'

const { Sider, Header, Content } = Layout

interface Props {
  username: string
  onLogout: () => void
}

const menuItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: 'Dashboard' },
  { key: '/products', icon: <ShoppingOutlined />, label: 'Products' },
  { key: '/crawler', icon: <ThunderboltOutlined />, label: 'Crawler' },
  { key: '/imports', icon: <CloudUploadOutlined />, label: 'Imports' },
  { key: '/audit', icon: <AuditOutlined />, label: 'Audit Log' },
]

export default function AdminLayout({ username, onLogout }: Props) {
  const navigate = useNavigate()
  const location = useLocation()

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={220} theme="dark">
        <div
          style={{
            padding: '16px 24px',
            color: '#fff',
            fontSize: 18,
            fontWeight: 600,
          }}
        >
          CPS Admin
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '0 24px',
            display: 'flex',
            justifyContent: 'flex-end',
            alignItems: 'center',
            gap: 16,
          }}
        >
          <Typography.Text>{username}</Typography.Text>
          <LogoutOutlined
            onClick={onLogout}
            style={{ cursor: 'pointer', fontSize: 18 }}
          />
        </Header>
        <Content style={{ margin: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
