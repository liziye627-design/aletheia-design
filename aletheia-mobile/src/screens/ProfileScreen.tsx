/**
 * Profile Screen - 我的
 * 显示登录信息与历史记录入口
 */

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  SafeAreaView,
  ScrollView,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';

import { Card, Button, CoreChatHeader } from '../components';
import { theme } from '../utils/theme';
import { useAuthStore } from '../store';
import type { RootStackParamList } from '../types';

type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

export const ProfileScreen: React.FC = () => {
  const navigation = useNavigation<NavigationProp>();
  const { user, logout, isLoading } = useAuthStore();

  const handleLogout = () => {
    Alert.alert('退出登录', '确认退出当前账号？', [
      { text: '取消', style: 'cancel' },
      {
        text: '退出',
        style: 'destructive',
        onPress: async () => {
          await logout();
        },
      },
    ]);
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" />
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <Text style={styles.title}>我的</Text>
        </View>

        <CoreChatHeader compact />

        <Card style={styles.userCard}>
          <View style={styles.avatar}>
            <Ionicons name="person" size={38} color={theme.colors.text.muted} />
          </View>
          <View style={styles.userInfo}>
            <Text style={styles.userName}>{user?.username || '未登录用户'}</Text>
            <Text style={styles.userEmail}>{user?.email || '暂无邮箱信息'}</Text>
          </View>
        </Card>

        <Card style={styles.entryCard}>
          <TouchableOpacity style={styles.entryRow} onPress={() => navigation.navigate('History')}>
            <View style={styles.entryIconWrap}>
              <Ionicons name="time-outline" size={20} color={theme.colors.primary.main} />
            </View>
            <View style={styles.entryContent}>
              <Text style={styles.entryTitle}>历史记录</Text>
              <Text style={styles.entrySubTitle}>查看所有已生成文章（辟谣/认可）</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={theme.colors.text.muted} />
          </TouchableOpacity>

          <TouchableOpacity style={styles.entryRow} onPress={() => Alert.alert('提示', '该功能即将开放')}>
            <View style={styles.entryIconWrap}>
              <Ionicons name="bookmark-outline" size={20} color={theme.colors.brand.success} />
            </View>
            <View style={styles.entryContent}>
              <Text style={styles.entryTitle}>我的收藏</Text>
              <Text style={styles.entrySubTitle}>已标记的重要验真任务</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={theme.colors.text.muted} />
          </TouchableOpacity>
        </Card>

        <Button
          title="退出登录"
          onPress={handleLogout}
          loading={isLoading}
          variant="outline"
          style={styles.logoutButton}
          textStyle={styles.logoutButtonText}
        />
      </ScrollView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background.primary,
  },
  content: {
    paddingHorizontal: 16,
    paddingBottom: 110,
    gap: 12,
  },
  header: {
    paddingTop: 16,
    paddingBottom: 8,
  },
  title: {
    color: theme.colors.text.secondary,
    fontSize: theme.fontSize.hero,
    fontWeight: '800',
  },
  userCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    backgroundColor: theme.colors.background.tertiary,
  },
  avatar: {
    width: 68,
    height: 68,
    borderRadius: 34,
    backgroundColor: theme.colors.background.elevated,
    justifyContent: 'center',
    alignItems: 'center',
  },
  userInfo: {
    flex: 1,
    gap: 2,
  },
  userName: {
    color: theme.colors.text.primary,
    fontSize: theme.fontSize.xl,
    fontWeight: '700',
  },
  userEmail: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.base,
  },
  entryCard: {
    backgroundColor: theme.colors.background.tertiary,
    padding: 0,
  },
  entryRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border.default,
  },
  entryIconWrap: {
    width: 34,
    height: 34,
    borderRadius: 10,
    backgroundColor: theme.colors.background.elevated,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 10,
  },
  entryContent: {
    flex: 1,
    gap: 2,
  },
  entryTitle: {
    color: theme.colors.text.secondary,
    fontSize: theme.fontSize.lg,
    fontWeight: '600',
  },
  entrySubTitle: {
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.sm,
  },
  logoutButton: {
    marginTop: 8,
    borderColor: theme.colors.status.false,
  },
  logoutButtonText: {
    color: theme.colors.status.false,
  },
});

export default ProfileScreen;
