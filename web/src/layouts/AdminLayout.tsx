import {
  AuditOutlined,
  CloudUploadOutlined,
  DashboardOutlined,
  LogoutOutlined,
  ShoppingOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { Layout, Menu, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import LangSwitcher from '../components/LangSwitcher'

const { Sider, Header, Content } = Layout

interface Props {
  username: string
  onLogout: () => void
}

export default function AdminLayout({ username, onLogout }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()

  const menuItems = [
    { key: '/dashboard', icon: <DashboardOutlined />, label: t('nav.dashboard') },
    { key: '/products', icon: <ShoppingOutlined />, label: t('nav.products') },
    { key: '/crawler', icon: <ThunderboltOutlined />, label: t('nav.crawler') },
    { key: '/imports', icon: <CloudUploadOutlined />, label: t('nav.imports') },
    { key: '/audit', icon: <AuditOutlined />, label: t('nav.audit') },
  ]

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
          <LangSwitcher />
          <Typography.Text>{username}</Typography.Text>
          <LogoutOutlined
            onClick={onLogout}
            title={t('common.logout')}
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
