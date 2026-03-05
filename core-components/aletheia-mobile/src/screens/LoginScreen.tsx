/**
 * Login Screen - Based on aletheia-ui.pen design
 * Dark theme with WeChat and Email login options
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  SafeAreaView,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';

import { Button, Input } from '../components';
import { theme } from '../utils/theme';
import { useAuthStore } from '../store';

export const LoginScreen: React.FC = () => {
  const { login, loginWithWechat, isLoading } = useAuthStore();

  const [showEmailLogin, setShowEmailLogin] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const handleWechatLogin = async () => {
    try {
      await loginWithWechat();
      // Navigation will be handled by auth state change
    } catch (error: any) {
      Alert.alert('登录失败', error.message);
    }
  };

  const handleEmailLogin = async () => {
    if (!email.trim() || !password.trim()) {
      Alert.alert('提示', '请输入邮箱和密码');
      return;
    }

    try {
      await login(email, password);
      // Navigation will be handled by auth state change
    } catch (error: any) {
      Alert.alert('登录失败', error.message);
    }
  };

  if (showEmailLogin) {
    return (
      <SafeAreaView style={styles.container}>
        <StatusBar style="light" />
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.keyboardView}
        >
          {/* Back Button */}
          <TouchableOpacity
            style={styles.backButton}
            onPress={() => setShowEmailLogin(false)}
          >
            <Ionicons name="arrow-back" size={24} color={theme.colors.text.secondary} />
          </TouchableOpacity>

          <View style={styles.content}>
            {/* Header */}
            <View style={styles.emailHeader}>
              <Text style={styles.emailTitle}>邮箱登录</Text>
              <Text style={styles.emailSubtitle}>请输入账号信息继续</Text>
            </View>

            {/* Form */}
            <View style={styles.form}>
              <Input
                value={email}
                onChangeText={setEmail}
                placeholder="邮箱地址"
                keyboardType="email-address"
                autoCapitalize="none"
                icon="mail-outline"
              />

              <Input
                value={password}
                onChangeText={setPassword}
                placeholder="密码"
                secureTextEntry
                icon="lock-closed-outline"
              />

              <Button
                title="登录"
                onPress={handleEmailLogin}
                loading={isLoading}
                variant="primary"
                size="lg"
                style={styles.signInButton}
              />

              <TouchableOpacity style={styles.forgotPassword}>
                <Text style={styles.forgotPasswordText}>忘记密码？</Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* Footer */}
          <View style={styles.footer}>
              <Text style={styles.legalText}>登录即表示你同意《用户协议》和《隐私政策》</Text>
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" />
      <View style={styles.content}>
        {/* Brand Section */}
        <View style={styles.brandWrap}>
          <View style={styles.logo}>
            {/* Logo glow effect would be added with LinearGradient in production */}
          </View>
          <Text style={styles.appName}>ALETHEIA</Text>
          <Text style={styles.slogan}>真相核验引擎</Text>
        </View>

        {/* Login Buttons */}
        <View style={styles.buttonsContainer}>
          <Button
            title="微信登录"
            onPress={handleWechatLogin}
            variant="wechat"
            size="lg"
            loading={isLoading}
            icon={
              <Ionicons name="chatbubble-ellipses" size={24} color="#FFFFFF" />
            }
            style={styles.wechatButton}
          />

          <Button
            title="邮箱登录"
            onPress={() => setShowEmailLogin(true)}
            variant="secondary"
            size="lg"
            icon={
              <Ionicons name="mail-outline" size={20} color={theme.colors.text.secondary} />
            }
            style={styles.emailButton}
          />

          {/* Legal Text */}
          <Text style={styles.legalText}>登录即表示你同意《用户协议》和《隐私政策》</Text>
        </View>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background.primary,
  },
  keyboardView: {
    flex: 1,
  },
  backButton: {
    padding: 20,
  },
  content: {
    flex: 1,
    paddingHorizontal: 32,
    justifyContent: 'flex-end',
    paddingBottom: 64,
  },
  brandWrap: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 16,
  },
  logo: {
    width: 80,
    height: 80,
    backgroundColor: theme.colors.primary.main,
    borderRadius: 24,
    // Shadow/glow effect
    shadowColor: theme.colors.primary.glow,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.5,
    shadowRadius: 32,
    elevation: 16,
  },
  appName: {
    color: theme.colors.text.primary,
    fontSize: 24,
    fontWeight: '900',
    letterSpacing: 2,
  },
  slogan: {
    color: theme.colors.text.muted,
    fontSize: 14,
    fontWeight: '500',
  },
  buttonsContainer: {
    gap: 20,
    alignItems: 'center',
  },
  wechatButton: {
    width: '100%',
  },
  emailButton: {
    width: '100%',
  },
  legalText: {
    color: theme.colors.text.placeholder,
    fontSize: 11,
    textAlign: 'center',
    marginTop: 8,
  },
  emailHeader: {
    marginBottom: 32,
  },
  emailTitle: {
    color: theme.colors.text.primary,
    fontSize: 28,
    fontWeight: '800',
    marginBottom: 8,
  },
  emailSubtitle: {
    color: theme.colors.text.muted,
    fontSize: 14,
  },
  form: {
    gap: 16,
  },
  signInButton: {
    marginTop: 8,
  },
  forgotPassword: {
    alignSelf: 'center',
    marginTop: 8,
  },
  forgotPasswordText: {
    color: theme.colors.primary.main,
    fontSize: 14,
    fontWeight: '500',
  },
  footer: {
    paddingHorizontal: 32,
    paddingBottom: 32,
  },
});

export default LoginScreen;
