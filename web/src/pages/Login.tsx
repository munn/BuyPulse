import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Form, Input, Typography } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import LangSwitcher from '../components/LangSwitcher'
import { useLocaleContext } from '../i18n/useLocale'
import type { User } from '../types'

interface Props {
  onLogin: (username: string, password: string) => Promise<User>
}

export default function Login({ onLogin }: Props) {
  const { t } = useTranslation()
  const { syncAfterLogin } = useLocaleContext()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleFinish = async (values: {
    username: string
    password: string
  }) => {
    setLoading(true)
    setError(null)
    try {
      const user = await onLogin(values.username, values.password)
      await syncAfterLogin(user.locale)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      const errorMap: Record<string, string> = {
        'Invalid credentials': t('login.invalidCredentials'),
        'Too many login attempts': t('login.tooManyAttempts'),
      }
      setError(detail ? (errorMap[detail] ?? t('login.failed')) : t('login.failed'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        background: '#f0f2f5',
        position: 'relative',
      }}
    >
      <div style={{ position: 'absolute', top: 16, right: 16 }}>
        <LangSwitcher />
      </div>
      <Card style={{ width: 400 }}>
        <Typography.Title level={3} style={{ textAlign: 'center' }}>
          CPS Admin
        </Typography.Title>
        {error && (
          <Alert
            message={error}
            type="error"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}
        <Form onFinish={handleFinish}>
          <Form.Item
            name="username"
            rules={[{ required: true, message: t('login.usernameRequired') }]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder={t('login.username')}
              size="large"
            />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[{ required: true, message: t('login.passwordRequired') }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder={t('login.password')}
              size="large"
            />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              block
              size="large"
            >
              {t('login.submit')}
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
