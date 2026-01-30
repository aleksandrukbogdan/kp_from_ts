import React, { useState, useEffect } from 'react';
import {
  Container, Paper, Typography, Button, TextField,
  Box, CircularProgress, Table, TableBody, TableContainer,
  TableCell, TableHead, TableRow, IconButton, Chip,
  Dialog, DialogTitle, DialogContent, DialogActions,
  AppBar, Toolbar, Avatar, Menu, MenuItem, Divider,
  Alert, AlertTitle, Collapse
} from '@mui/material';
import {
  CloudUpload, CheckCircle, Add, Delete, Refresh, ArrowBack, Logout, Person, GetApp,
  Warning, Error as ErrorIcon, SyncProblem
} from '@mui/icons-material';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { config } from './config';
import MarkdownEditor from './MarkdownEditor';
import BudgetMatrix from './BudgetMatrix';

// Адрес FastAPI бэкенда (автоматически dev/prod)
const API_URL = config.API_URL;
axios.defaults.withCredentials = true;

// Функция для получения имени пользователя из cookie
function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return decodeURIComponent(parts.pop().split(';').shift());
  return null;
}

// Helper to format data (arrays) to multiline string
const formatDataToString = (val) => {
  if (Array.isArray(val)) return val.join('\n');
  return val || '';
};

export default function AgentKP() {
  const navigate = useNavigate();
  const [file, setFile] = useState(null);
  const [workflowId, setWorkflowId] = useState(null);
  const [status, setStatus] = useState(null);
  const [data, setData] = useState(null);
  const [finalDoc, setFinalDoc] = useState(null);

  // User state
  const [username, setUsername] = useState('');
  const [anchorEl, setAnchorEl] = useState(null);

  // --- Состояние Сметы ---
  const [roles, setRoles] = useState({ "Менеджер": 2500, "ML-Инженер": 3500, "Frontend": 3000 });
  const [stages, setStages] = useState(["Сбор данных", "Прототип", "Разработка", "Тестирование"]);
  const [budgetMatrix, setBudgetMatrix] = useState({}); // { "StageName": { "RoleName": hours } }

  // Состояние диалогов (модалок)
  const [openRoleDialog, setOpenRoleDialog] = useState(false);
  const [openStageDialog, setOpenStageDialog] = useState(false);
  const [newRoleName, setNewRoleName] = useState("");
  const [newRoleRate, setNewRoleRate] = useState(2500);
  const [newStageName, setNewStageName] = useState("");

  // --- Новые состояния для фич ---
  const [requirementIssues, setRequirementIssues] = useState([]);
  const [sourceExcerpts, setSourceExcerpts] = useState({});
  const [rawText, setRawText] = useState('');
  const [suggestedHours, setSuggestedHours] = useState({});
  const [selectedItem, setSelectedItem] = useState(null);  // {field, text, source} - выбранный пункт
  const [userModified, setUserModified] = useState({});  // {этап: {роль: true/false}}

  // Хелпер: найти issue для пункта (Нечеткое сравнение)
  const getIssueForItem = (fieldName, itemText) => {
    if (!itemText) return null;
    const cleanItem = itemText.toLowerCase().trim();

    return requirementIssues.find(issue => {
      if (issue.field !== fieldName) return false;
      if (!issue.item_text) return false;

      const cleanIssueText = issue.item_text.toLowerCase().trim();
      // 1. Точное совпадение (с очисткой)
      if (cleanItem === cleanIssueText) return true;
      // 2. Частичное совпадение (если LLM сократил или изменил пару слов)
      // Проверяем, содержится ли одна строка в другой (достаточно длинная)
      if (cleanItem.length > 10 && cleanIssueText.length > 10) {
        return cleanItem.includes(cleanIssueText) || cleanIssueText.includes(cleanItem);
      }
      return false;
    });
  };

  useEffect(() => {
    const user = getCookie('portal_user');
    if (user) {
      setUsername(user);
    } else {
      // Если пользователь не авторизован - перенаправляем на логин
      navigate('/login');
    }
  }, [navigate]);

  const handleMenuOpen = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
  };

  const handleLogout = () => {
    document.cookie = 'portal_auth_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    document.cookie = 'portal_user=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    window.location.href = '/login';
  };

  // --- 1. ЗАГРУЗКА ФАЙЛА ---
  const handleUpload = async () => {
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);

    try {
      // Отправляем файл на FastAPI
      const res = await axios.post(`${API_URL}/start`, formData);
      setWorkflowId(res.data.workflow_id);
      setStatus("PROCESSING");
    } catch (err) {
      alert("Ошибка соединения с сервером: " + err.message);
    }
  };

  // --- 2. ОПРОС СТАТУСА (Long Polling) ---
  useEffect(() => {
    if (!workflowId || status === "COMPLETED") return;

    const interval = setInterval(async () => {
      try {
        const res = await axios.get(`${API_URL}/status/${workflowId}`);
        const state = res.data;

        setStatus(state.status);

        // Когда ИИ закончил анализ, сохраняем данные
        if (state.status === "WAITING_FOR_HUMAN" && state.extracted_data && !data) {
          const raw = state.extracted_data;

          // Helper: Safely extract string from different formats (string | object)
          const safelyExtractText = (val) => {
            if (!val) return '';
            if (typeof val === 'string') return val;
            if (typeof val === 'object') return val.text || '';
            return String(val);
          };

          // Helper: Extract source from object if available
          const safelyExtractSource = (val) => {
            if (val && typeof val === 'object') return val.source || '';
            return '';
          };

          // Helper: Normalize arrays (handles string/array/object mix)
          const extractTextArray = (val) => {
            if (!val) return [];
            if (Array.isArray(val)) {
              return val.map(item => typeof item === 'object' ? (item.text || '') : item);
            }
            if (typeof val === 'string') return [val]; // Handle single string as array
            return [];
          };

          // Helper: Normalize to objects for _original (UI expects {text, source})
          const normalizeToObjects = (val) => {
            if (!val) return [];
            let arr = [];
            if (Array.isArray(val)) arr = val;
            else if (typeof val === 'string') arr = [val];

            return arr.map(item => {
              if (typeof item === 'string') return { text: item, source: '' };
              if (typeof item === 'object') return { text: item.text || '', source: item.source || '' };
              return { text: '', source: '' };
            });
          };

          // Извлечение текста из категоризированной структуры key_features
          const extractCategorizedFeatures = (obj) => {
            if (!obj || typeof obj !== 'object') return '';
            if (Array.isArray(obj)) {
              // Fallback для старой структуры (массив)
              return extractTextArray(obj).join('\n');
            }
            // Новая структура с категориями
            const allTexts = [];
            Object.values(obj).forEach(categoryArr => {
              if (Array.isArray(categoryArr)) {
                categoryArr.forEach(item => {
                  allTexts.push(typeof item === 'object' ? (item.text || '') : item);
                });
              }
            });
            return allTexts.join('\n');
          };

          // Преобразуем категоризированную структуру в плоский массив для отображения
          const flattenCategorizedFeatures = (obj) => {
            if (!obj || typeof obj !== 'object') return [];
            if (Array.isArray(obj)) return normalizeToObjects(obj); // Fallback for old structure
            const allItems = [];
            Object.entries(obj).forEach(([category, items]) => {
              if (Array.isArray(items)) {
                items.forEach(item => {
                  const normalized = typeof item === 'string' ? { text: item, source: '' } : (item || { text: '', source: '' });
                  allItems.push({ ...normalized, category });
                });
              }
            });
            return allItems;
          };

          const formattedData = {
            ...raw,
            client_name: safelyExtractText(raw.client_name),
            project_essence: safelyExtractText(raw.project_essence),
            project_type: safelyExtractText(raw.project_type),
            business_goals: extractTextArray(raw.business_goals).join('\n'),
            key_features: extractCategorizedFeatures(raw.key_features),
            tech_stack: extractTextArray(raw.tech_stack).join('\n'),
            client_integrations: extractTextArray(raw.client_integrations).join('\n'),
            // Сохраняем оригинальные массивы для показа цитат
            _original: {
              ...raw,
              // Top-level fields with source
              client_name: raw.client_name,
              project_essence: raw.project_essence,
              project_type: raw.project_type,

              tech_stack: normalizeToObjects(raw.tech_stack),
              business_goals: normalizeToObjects(raw.business_goals),
              client_integrations: normalizeToObjects(raw.client_integrations),
              key_features_flat: flattenCategorizedFeatures(raw.key_features)
            }
          };
          setData(formattedData);

          // Сохраняем новые данные
          setRequirementIssues(raw.requirement_issues || []);
          // sourceExcerpts больше не нужны, берем из _original
          setRawText(state.raw_text_preview || '');
          setSuggestedHours(state.suggested_hours || {});

          // Используем этапы и роли, предложенные ИИ
          const aiStages = state.suggested_stages || ["Сбор данных", "Прототип", "Разработка", "Тестирование"];
          const aiRoles = state.suggested_roles || ["Менеджер", "Frontend", "Backend", "Дизайнер"];

          setStages(aiStages);
          // Инициализируем роли с дефолтными ставками
          const defaultRates = {
            "Менеджер проекта": 2500,
            "Системный аналитик": 2800,
            "Дизайнер UI/UX": 2800,
            "Frontend-разработчик": 3000,
            "Backend-разработчик": 3000,
            "Fullstack-разработчик": 3200,
            "ML-инженер": 3500,
            "DevOps-инженер": 3200,
            "QA-инженер": 2200,
          };
          const rolesWithRates = {};
          aiRoles.forEach(r => {
            rolesWithRates[r] = defaultRates[r] || 2500; // дефолтная ставка если роль неизвестна
          });
          setRoles(rolesWithRates);

          // Инициализируем матрицу подсказками от ИИ
          const initialMatrix = {};
          const suggestedMatrix = state.suggested_hours || {};
          aiStages.forEach(s => {
            initialMatrix[s] = {};
            aiRoles.forEach(r => {
              initialMatrix[s][r] = suggestedMatrix[s]?.[r] || 0;
            });
          });
          setBudgetMatrix(initialMatrix);

          // Инициализируем userModified как false для всех ячеек
          const initialModified = {};
          aiStages.forEach(s => {
            initialModified[s] = {};
            aiRoles.forEach(r => initialModified[s][r] = false);
          });
          setUserModified(initialModified);
        }

        // Когда все готово
        if (state.status === "COMPLETED") {
          setFinalDoc(state.final_proposal);
          clearInterval(interval);
        }
      } catch (err) {
        // При 404 (workflow не найден) останавливаем опрос
        if (err.response?.status === 404) {
          clearInterval(interval);
        } else {
          console.error("Ошибка опроса:", err);
        }
      }
    }, 2000); // Спрашиваем каждые 2 секунды

    return () => clearInterval(interval);
  }, [workflowId, status, data]);

  // --- 3. ЛОГИКА ТАБЛИЦЫ ---
  const handleHourChange = (stage, role, value) => {
    const val = parseInt(value) || 0;
    setBudgetMatrix(prev => ({
      ...prev,
      [stage]: {
        ...prev[stage],
        [role]: val
      }
    }));
    // Помечаем ячейку как изменённую пользователем
    setUserModified(prev => ({
      ...prev,
      [stage]: {
        ...prev[stage],
        [role]: true
      }
    }));
  };

  const calculateTotal = () => {
    let total = 0;
    Object.keys(budgetMatrix).forEach(stage => {
      Object.keys(roles).forEach(role => {
        const hours = budgetMatrix[stage]?.[role] || 0;
        const rate = roles[role];
        total += hours * rate;
      });
    });
    return total;
  };

  // Добавление роли
  const handleAddRole = () => {
    if (newRoleName && !roles[newRoleName]) {
      setRoles({ ...roles, [newRoleName]: Number(newRoleRate) });
      setOpenRoleDialog(false);
      setNewRoleName("");
    }
  };

  // Добавление этапа
  const handleAddStage = () => {
    if (newStageName && !stages.includes(newStageName)) {
      setStages([...stages, newStageName]);
      // Добавляем новую строку в матрицу
      setBudgetMatrix({ ...budgetMatrix, [newStageName]: {} });
      setOpenStageDialog(false);
      setNewStageName("");
    }
  };

  // Удаление роли
  const handleDeleteRole = (roleToDelete) => {
    const { [roleToDelete]: deleted, ...remainingRoles } = roles;
    setRoles(remainingRoles);

    // Удаляем из матрицы
    const newMatrix = { ...budgetMatrix };
    Object.keys(newMatrix).forEach(stage => {
      if (newMatrix[stage]) {
        const { [roleToDelete]: val, ...rest } = newMatrix[stage];
        newMatrix[stage] = rest;
      }
    });
    setBudgetMatrix(newMatrix);
  };

  // Удаление этапа
  const handleDeleteStage = (stageToDelete) => {
    setStages(stages.filter(s => s !== stageToDelete));
    const { [stageToDelete]: deleted, ...remainingMatrix } = budgetMatrix;
    setBudgetMatrix(remainingMatrix);
  };

  // --- 5. СКАЧИВАНИЕ DOCX ---
  const handleDownload = async () => {
    try {
      const response = await axios.post(`${API_URL}/download_docx`, {
        text: finalDoc
      }, {
        responseType: 'blob' // Важно для скачивания файла
      });

      // Создаем ссылку для скачивания
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'Offer_KP.docx');
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      alert("Ошибка скачивания: " + err.message);
    }
  };

  // --- 4. ОТПРАВКА УТВЕРЖДЕНИЯ ---
  const handleApprove = async () => {
    try {
      await axios.post(`${API_URL}/approve/${workflowId}`, {
        updated_data: data,
        budget: budgetMatrix,
        rates: roles
      });
      setStatus("GENERATING"); // Локально меняем статус, чтобы показать спиннер
    } catch (err) {
      alert("Ошибка отправки: " + err.message);
    }
  };

  // --- РЕНДЕРИНГ (UI) ---
  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', bgcolor: 'background.default' }}>
      {/* Header */}
      <AppBar
        position="static"
        elevation={0}
        sx={{
          backgroundColor: 'white',
          borderBottom: '1px solid',
          borderColor: 'divider',
        }}
      >
        <Toolbar sx={{ justifyContent: 'space-between', px: { xs: 2, md: 4 } }}>
          {/* Logo & Back */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <IconButton onClick={() => navigate('/')} sx={{ color: 'text.primary' }}>
              <ArrowBack />
            </IconButton>
            <Box
              component="img"
              src="/logo.svg"
              alt="НИР-центр"
              sx={{ height: 28 }}
            />
          </Box>

          {/* Title */}
          <Typography
            variant="h6"
            sx={{
              color: 'primary.main',
              fontWeight: 600,
              position: 'absolute',
              left: '50%',
              transform: 'translateX(-50%)',
              display: { xs: 'none', md: 'block' }
            }}
          >
            Агент КП
          </Typography>

          {/* User Menu */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            {workflowId && (
              <Chip
                label={`ID: ${workflowId.slice(0, 20)}...`}
                variant="outlined"
                size="small"
                sx={{ display: { xs: 'none', sm: 'flex' } }}
              />
            )}
            <IconButton onClick={handleMenuOpen} sx={{ gap: 1, borderRadius: 2, px: 1.5 }}>
              <Avatar
                sx={{
                  width: 32,
                  height: 32,
                  bgcolor: 'primary.main',
                  fontSize: '0.875rem',
                }}
              >
                {username ? username.charAt(0).toUpperCase() : <Person />}
              </Avatar>
            </IconButton>

            <Menu
              anchorEl={anchorEl}
              open={Boolean(anchorEl)}
              onClose={handleMenuClose}
              transformOrigin={{ horizontal: 'right', vertical: 'top' }}
              anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
              PaperProps={{ sx: { mt: 1, minWidth: 180 } }}
            >
              <MenuItem disabled>
                <Typography variant="body2" color="text.secondary">
                  {username}
                </Typography>
              </MenuItem>
              <Divider />
              <MenuItem onClick={handleLogout} sx={{ color: 'error.main' }}>
                <Logout fontSize="small" sx={{ mr: 1.5 }} />
                Выйти
              </MenuItem>
            </Menu>
          </Box>
        </Toolbar>
      </AppBar>

      {/* Main Content */}
      <Container maxWidth="lg" sx={{ py: 4, flex: 1 }}>

        {/* БЛОК 1: ЗАГРУЗКА */}
        {!workflowId && (
          <Paper
            elevation={0}
            sx={{
              p: 8,
              textAlign: 'center',
              border: '2px dashed',
              borderColor: 'primary.main',
              borderRadius: 4,
              bgcolor: 'rgba(255, 107, 0, 0.02)',
            }}
          >
            <CloudUpload sx={{ fontSize: 80, color: 'primary.main', mb: 3, opacity: 0.8 }} />
            <Typography variant="h5" gutterBottom fontWeight={600}>
              Загрузите Техническое Задание
            </Typography>
            <Typography color="text.secondary" paragraph sx={{ mb: 4 }}>
              Поддерживаются форматы PDF, DOCX и TXT
            </Typography>

            <input
              accept=".pdf,.docx,.txt"
              style={{ display: 'none' }}
              id="upload-file"
              type="file"
              onChange={(e) => setFile(e.target.files[0])}
            />
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
              <label htmlFor="upload-file">
                <Button variant="outlined" component="span" size="large" sx={{ px: 4 }}>
                  {file ? file.name : "Выбрать файл"}
                </Button>
              </label>
              <Button
                variant="contained"
                size="large"
                onClick={handleUpload}
                disabled={!file}
                startIcon={<CheckCircle />}
                sx={{ px: 5 }}
              >
                Запустить анализ
              </Button>
            </Box>
          </Paper>
        )}

        {/* БЛОК 2: ЗАГРУЗКА / ОЖИДАНИЕ */}
        {(status === "PROCESSING" || status === "GENERATING") && (
          <Paper elevation={0} sx={{ p: 10, textAlign: 'center', borderRadius: 4 }}>
            <CircularProgress size={64} thickness={4} sx={{ color: 'primary.main', mb: 4 }} />
            <Typography variant="h5" color="text.primary" fontWeight={500}>
              {status === "PROCESSING"
                ? "ИИ анализирует документ..."
                : "Генерация финального документа..."}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              Это может занять несколько минут
            </Typography>
          </Paper>
        )}

        {/* БЛОК 3: ПРОВЕРКА (HUMAN IN THE LOOP) */}
        {status === "WAITING_FOR_HUMAN" && data && (
          <Paper elevation={0} sx={{ p: 0, bgcolor: 'transparent' }}>

            {/* Основной layout: контент + боковая панель */}
            <Box display="flex" gap={3}>

              {/* Левая часть: основной контент */}
              <Box flex={2}>
                <Container maxWidth="md" disableGutters>
                  <Typography variant="h4" gutterBottom fontWeight={700} sx={{ mb: 3, letterSpacing: '-0.02em' }}>
                    Проверка данных
                  </Typography>

                  {/* БЛОК ПРОБЛЕМНЫХ ТРЕБОВАНИЙ */}
                  {requirementIssues.length > 0 && (
                    <Paper
                      elevation={0}
                      sx={{
                        p: 2.5,
                        mb: 3,
                        bgcolor: '#FFF8E1', // Amber 50
                        borderRadius: 2,
                        border: '1px solid',
                        borderColor: '#FFE082' // Amber 200
                      }}
                    >
                      <Box display="flex" alignItems="center" gap={1} mb={2}>
                        <Warning sx={{ color: '#F57C00' }} />
                        <Typography variant="h6" fontWeight={600} color="#E65100">
                          Проблемные требования ({requirementIssues.length})
                        </Typography>
                      </Box>

                      <Box display="flex" flexDirection="column" gap={1.5}>
                        {requirementIssues.map((issue, idx) => {
                          // Определяем стиль в зависимости от типа проблемы
                          const getIssueStyle = (type) => {
                            switch (type) {
                              case 'questionable':
                                return {
                                  severity: 'warning',
                                  icon: <Warning fontSize="small" />,
                                  label: 'Неясное требование',
                                  color: '#ED6C02'
                                };
                              case 'impossible':
                                return {
                                  severity: 'error',
                                  icon: <ErrorIcon fontSize="small" />,
                                  label: 'Нереализуемое',
                                  color: '#D32F2F'
                                };
                              case 'contradictory':
                                return {
                                  severity: 'info',
                                  icon: <SyncProblem fontSize="small" />,
                                  label: 'Противоречие',
                                  color: '#0288D1'
                                };
                              default:
                                return {
                                  severity: 'warning',
                                  icon: <Warning fontSize="small" />,
                                  label: 'Проблема',
                                  color: '#ED6C02'
                                };
                            }
                          };
                          const style = getIssueStyle(issue.type);

                          return (
                            <Alert
                              key={idx}
                              severity={style.severity}
                              icon={style.icon}
                              sx={{
                                '& .MuiAlert-message': { width: '100%' },
                                borderRadius: 1.5
                              }}
                            >
                              <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={0.5}>
                                <AlertTitle sx={{ fontWeight: 600, mb: 0 }}>{style.label}</AlertTitle>
                                {issue.field && (
                                  <Chip label={issue.field.replace(/_/g, ' ')} size="small" variant="outlined" sx={{ textTransform: 'capitalize' }} />
                                )}
                              </Box>
                              <Typography variant="body2" sx={{ mb: 0.5 }}>
                                <strong>Текст:</strong> {issue.item_text || issue.text}
                              </Typography>
                              <Typography variant="body2" color="text.secondary">
                                <strong>Причина:</strong> {issue.reason}
                              </Typography>
                            </Alert>
                          );
                        })}
                      </Box>
                    </Paper>
                  )}

                  {/* BENTO GRID LAYOUT */}
                  <Box display="grid" gridTemplateColumns={{ xs: '1fr', md: '1fr 1fr' }} gap={3} sx={{ mb: 4 }}>

                    {/* 1. КЛИЕНТ */}
                    <Paper
                      elevation={0}
                      onClick={() => setSelectedItem({ field: 'client_name', text: data.client_name, source: data._original?.client_name?.source })}
                      sx={{
                        p: 2,
                        bgcolor: selectedItem?.field === 'client_name' ? 'rgba(25, 118, 210, 0.08)' : 'white',
                        borderRadius: 2,
                        border: '1px solid',
                        borderColor: selectedItem?.field === 'client_name' ? 'primary.main' : 'divider',
                        cursor: 'pointer',
                        transition: 'all 0.2s ease',
                        '&:hover': { borderColor: 'primary.light', bgcolor: 'rgba(25, 118, 210, 0.04)' },
                        alignSelf: 'start'
                      }}
                    >
                      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1, pl: 0.5, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        Клиент
                      </Typography>
                      <TextField
                        fullWidth
                        hiddenLabel
                        variant="filled"
                        value={data.client_name || ''}
                        onChange={(e) => setData({ ...data, client_name: e.target.value })}
                        onClick={(e) => e.stopPropagation()}
                        InputProps={{ disableUnderline: true, sx: { borderRadius: 1.5, bgcolor: 'grey.50' } }}
                      />
                    </Paper>

                    {/* 2. СТЕК ТЕХНОЛОГИЙ (Span 2 rows on Desktop) */}
                    <Paper
                      elevation={0}
                      sx={{
                        gridRow: { md: 'span 2' },
                        p: 2,
                        bgcolor: !data.tech_stack ? '#FFF3E0' : 'white',
                        borderRadius: 2,
                        border: '1px solid',
                        borderColor: !data.tech_stack ? '#FFCC80' : 'divider',
                        display: 'flex',
                        flexDirection: 'column'
                      }}
                    >
                      <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                        <Typography variant="subtitle2" color="text.secondary" sx={{ pl: 0.5, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                          Стек технологий
                        </Typography>
                        {!data.tech_stack && (
                          <Chip label="Не указан" size="small" color="warning" variant="outlined" />
                        )}
                      </Box>
                      {/* Кликабельные чипы для стека */}
                      {data._original?.tech_stack?.length > 0 && (
                        <Box display="flex" flexWrap="wrap" gap={0.5} mb={1.5} sx={{ flex: 1, alignContent: 'flex-start' }}>
                          {data._original.tech_stack.map((item, idx) => {
                            const isSelected = selectedItem?.field === 'tech_stack' && selectedItem?.text === item.text;
                            return (
                              <Chip
                                key={idx}
                                label={item.text}
                                size="small"
                                onClick={() => setSelectedItem({ field: 'tech_stack', text: item.text, source: item.source })}
                                variant={isSelected ? 'filled' : 'outlined'}
                                color={isSelected ? 'primary' : 'default'}
                                sx={{ cursor: 'pointer' }}
                              />
                            );
                          })}
                        </Box>
                      )}
                      <TextField
                        fullWidth
                        hiddenLabel
                        variant="filled"
                        size="small"
                        multiline
                        minRows={3}
                        value={data.tech_stack || ''}
                        onChange={(e) => setData({ ...data, tech_stack: e.target.value })}
                        placeholder="Добавить технологии..."
                        helperText={!data.tech_stack ? "Если не указано в ТЗ, добавьте вручную" : ""}
                        InputProps={{ disableUnderline: true, sx: { borderRadius: 1.5, bgcolor: !data.tech_stack ? 'white' : 'grey.50', fontSize: '0.85rem', alignItems: 'flex-start' } }}
                        FormHelperTextProps={{ sx: { ml: 0, mt: 1, color: 'text.secondary' } }}
                      />
                    </Paper>

                    {/* 2.5. ТИП ПРОЕКТА (Col 1, Row 2) */}
                    <Paper
                      elevation={0}
                      sx={{
                        p: 2,
                        bgcolor: 'white',
                        borderRadius: 2,
                        border: '1px solid',
                        borderColor: 'divider',
                        alignSelf: 'start'
                      }}
                    >
                      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1, pl: 0.5, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        Тип проекта
                      </Typography>
                      <TextField
                        fullWidth
                        hiddenLabel
                        variant="filled"
                        value={data.project_type || ''}
                        onChange={(e) => setData({ ...data, project_type: e.target.value })}
                        InputProps={{ disableUnderline: true, sx: { borderRadius: 1.5, bgcolor: 'grey.50' } }}
                      />
                    </Paper>

                    {/* 3. СУТЬ ПРОЕКТА (Full Width) */}
                    <Paper
                      elevation={0}
                      onClick={() => setSelectedItem({ field: 'project_essence', text: data.project_essence, source: data._original?.project_essence?.source })}
                      sx={{
                        gridColumn: '1 / -1',
                        p: 3,
                        bgcolor: selectedItem?.field === 'project_essence' ? 'rgba(25, 118, 210, 0.08)' : 'white',
                        borderRadius: 3,
                        border: '1px solid',
                        borderColor: selectedItem?.field === 'project_essence' ? 'primary.main' : 'divider',
                        cursor: 'pointer',
                        transition: 'all 0.2s ease',
                        '&:hover': { borderColor: 'primary.light' }
                      }}
                    >
                      <Typography variant="h6" fontWeight={600} gutterBottom>
                        Суть проекта
                      </Typography>
                      <TextField
                        fullWidth
                        hiddenLabel
                        multiline
                        variant="filled"
                        minRows={2}
                        value={data.project_essence || ''}
                        onChange={(e) => setData({ ...data, project_essence: e.target.value })}
                        onClick={(e) => e.stopPropagation()}
                        InputProps={{ disableUnderline: true, sx: { borderRadius: 2, bgcolor: 'grey.50' } }}
                      />
                    </Paper>

                    {/* 4. БИЗНЕС ЗАДАЧИ — список кликабельных пунктов */}
                    <Paper elevation={0} sx={{ gridColumn: '1 / -1', p: 3, bgcolor: 'white', borderRadius: 3, border: '1px solid', borderColor: 'divider' }}>
                      <Typography variant="h6" fontWeight={600} gutterBottom>
                        Бизнес-задачи
                      </Typography>
                      <Box display="flex" flexDirection="column" gap={1}>
                        {data._original?.business_goals?.map((item, idx) => {
                          const issue = getIssueForItem('business_goals', item.text);
                          const isSelected = selectedItem?.field === 'business_goals' && selectedItem?.text === item.text;
                          return (
                            <Box
                              key={idx}
                              onClick={() => setSelectedItem({ field: 'business_goals', text: item.text, source: item.source, issue })}
                              sx={{
                                p: 1.5,
                                borderRadius: 1.5,
                                cursor: 'pointer',
                                border: '1px solid',
                                borderColor: isSelected ? 'primary.main' : (issue ? (issue.type === 'impossible' ? '#D32F2F' : issue.type === 'contradictory' ? '#0288D1' : '#ED6C02') : 'divider'),
                                bgcolor: isSelected ? 'rgba(25, 118, 210, 0.08)' : (issue ? (issue.type === 'impossible' ? '#FFEBEE' : issue.type === 'contradictory' ? '#E3F2FD' : '#FFF8E1') : 'grey.50'),
                                transition: 'all 0.2s ease',
                                '&:hover': { borderColor: issue ? undefined : 'primary.light', bgcolor: isSelected ? undefined : 'rgba(25, 118, 210, 0.04)' }
                              }}
                            >
                              <Box display="flex" alignItems="center" gap={1}>
                                {issue && (
                                  issue.type === 'impossible' ? <ErrorIcon fontSize="small" sx={{ color: '#D32F2F' }} /> :
                                    issue.type === 'contradictory' ? <SyncProblem fontSize="small" sx={{ color: '#0288D1' }} /> :
                                      <Warning fontSize="small" sx={{ color: '#ED6C02' }} />
                                )}
                                <Typography variant="body2">{item.text}</Typography>
                              </Box>
                            </Box>
                          );
                        })}
                      </Box>
                      {/* Текстовое поле для редактирования (сворачиваемое) */}
                      <TextField
                        fullWidth
                        hiddenLabel
                        multiline
                        variant="filled"
                        size="small"
                        minRows={2}
                        value={data.business_goals || ''}
                        onChange={(e) => setData({ ...data, business_goals: e.target.value })}
                        placeholder="Добавить/редактировать..."
                        sx={{ mt: 2 }}
                        InputProps={{ disableUnderline: true, sx: { borderRadius: 1.5, bgcolor: 'grey.50', fontSize: '0.85rem' } }}
                      />
                    </Paper>

                    {/* 5. КЛЮЧЕВОЙ ФУНКЦИОНАЛ — список кликабельных пунктов с категориями */}
                    <Paper elevation={0} sx={{ gridColumn: '1 / -1', p: 3, bgcolor: 'rgba(25, 118, 210, 0.05)', borderRadius: 3 }}>
                      <Box display="flex" alignItems="center" gap={1} mb={2}>
                        <Typography variant="h6" fontWeight={600} color="primary.main">
                          Ключевой функционал
                        </Typography>
                        <Chip
                          label={`${data._original?.key_features_flat?.length || 0} требований`}
                          size="small"
                          color="primary"
                        />
                      </Box>

                      {/* Категории */}
                      {(() => {
                        const features = data._original?.key_features_flat || [];
                        const categories = [...new Set(features.map(f => f.category).filter(Boolean))];
                        // Material 3 стиль категорий с иконками и цветами
                        const categoryConfig = {
                          modules: { label: 'Модули', color: '#6750A4', bgColor: 'rgba(103, 80, 164, 0.08)' },
                          screens: { label: 'Экраны', color: '#0061A4', bgColor: 'rgba(0, 97, 164, 0.08)' },
                          reports: { label: 'Отчёты', color: '#006E1C', bgColor: 'rgba(0, 110, 28, 0.08)' },
                          integrations: { label: 'Интеграции', color: '#BA1A1A', bgColor: 'rgba(186, 26, 26, 0.08)' },
                          nfr: { label: 'Нефункциональные требования', color: '#5D5F5F', bgColor: 'rgba(93, 95, 95, 0.08)' }
                        };

                        if (categories.length === 0) {
                          // Fallback: показываем как раньше без категорий
                          return (
                            <Box display="flex" flexDirection="column" gap={1}>
                              {features.map((item, idx) => {
                                const issue = getIssueForItem('key_features', item.text);
                                const isSelected = selectedItem?.field === 'key_features' && selectedItem?.text === item.text;
                                return (
                                  <Box
                                    key={idx}
                                    onClick={() => setSelectedItem({ field: 'key_features', text: item.text, source: item.source, issue })}
                                    sx={{
                                      p: 1.5,
                                      borderRadius: 1.5,
                                      cursor: 'pointer',
                                      border: '1px solid',
                                      borderColor: isSelected ? 'primary.main' : (issue ? '#ED6C02' : 'transparent'),
                                      bgcolor: isSelected ? 'rgba(25, 118, 210, 0.12)' : (issue ? '#FFF8E1' : 'white'),
                                      transition: 'all 0.2s ease',
                                      '&:hover': { bgcolor: isSelected ? undefined : 'rgba(25, 118, 210, 0.08)' }
                                    }}
                                  >
                                    <Box display="flex" alignItems="center" justifyContent="space-between" gap={1}>
                                      <Box display="flex" alignItems="center" gap={1} flex={1}>
                                        {issue && <Warning fontSize="small" sx={{ color: '#ED6C02' }} />}
                                        <Typography variant="body2">{item.text}</Typography>
                                      </Box>
                                      {item.estimated_hours && (
                                        <Chip size="small" label={`${item.estimated_hours} ч`}
                                          sx={{ bgcolor: 'rgba(25, 118, 210, 0.1)', color: 'primary.main', fontWeight: 600, fontSize: '0.7rem', height: 24, minWidth: 48 }} />
                                      )}
                                    </Box>
                                  </Box>
                                );
                              })}
                            </Box>
                          );
                        }

                        // Показываем по категориям с Material 3 стилем
                        return categories.map(cat => {
                          const catFeatures = features.filter(f => f.category === cat);
                          if (catFeatures.length === 0) return null;
                          const config = categoryConfig[cat] || { label: cat, color: '#1976D2', bgColor: 'rgba(25, 118, 210, 0.08)' };

                          return (
                            <Box key={cat} sx={{ mb: 2.5 }}>
                              {/* Material 3 категория header */}
                              <Box
                                sx={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 1.5,
                                  mb: 1.5,
                                  pb: 1,
                                  borderBottom: `2px solid ${config.color}20`
                                }}
                              >
                                <Box
                                  sx={{
                                    width: 4,
                                    height: 20,
                                    borderRadius: 2,
                                    bgcolor: config.color
                                  }}
                                />
                                <Typography
                                  variant="subtitle2"
                                  sx={{
                                    color: config.color,
                                    fontWeight: 600,
                                    letterSpacing: '0.02em'
                                  }}
                                >
                                  {config.label}
                                </Typography>
                                <Chip
                                  label={catFeatures.length}
                                  size="small"
                                  sx={{
                                    height: 22,
                                    fontSize: '0.75rem',
                                    fontWeight: 600,
                                    bgcolor: config.bgColor,
                                    color: config.color,
                                    border: 'none'
                                  }}
                                />
                              </Box>
                              <Box display="flex" flexDirection="column" gap={0.75}>
                                {catFeatures.map((item, idx) => {
                                  const issue = getIssueForItem('key_features', item.text);
                                  const isSelected = selectedItem?.field === 'key_features' && selectedItem?.text === item.text;
                                  return (
                                    <Box
                                      key={idx}
                                      onClick={() => setSelectedItem({ field: 'key_features', text: item.text, source: item.source, issue, category: cat })}
                                      sx={{
                                        p: 1.25,
                                        borderRadius: 1.5,
                                        cursor: 'pointer',
                                        border: '1px solid',
                                        borderColor: isSelected ? 'primary.main' : (issue ? (issue.type === 'impossible' ? '#D32F2F' : issue.type === 'contradictory' ? '#0288D1' : '#ED6C02') : 'transparent'),
                                        bgcolor: isSelected ? 'rgba(25, 118, 210, 0.12)' : (issue ? (issue.type === 'impossible' ? '#FFEBEE' : issue.type === 'contradictory' ? '#E3F2FD' : '#FFF8E1') : 'white'),
                                        transition: 'all 0.2s ease',
                                        '&:hover': { bgcolor: isSelected ? undefined : 'rgba(25, 118, 210, 0.08)' }
                                      }}
                                    >
                                      <Box display="flex" alignItems="center" justifyContent="space-between" gap={1}>
                                        <Box display="flex" alignItems="center" gap={1} flex={1}>
                                          {issue && (
                                            issue.type === 'impossible' ? <ErrorIcon fontSize="small" sx={{ color: '#D32F2F' }} /> :
                                              issue.type === 'contradictory' ? <SyncProblem fontSize="small" sx={{ color: '#0288D1' }} /> :
                                                <Warning fontSize="small" sx={{ color: '#ED6C02' }} />
                                          )}
                                          <Typography variant="body2">{item.text}</Typography>
                                        </Box>
                                        {item.estimated_hours && (
                                          <Chip
                                            size="small"
                                            label={`${item.estimated_hours} ч`}
                                            sx={{
                                              bgcolor: 'rgba(25, 118, 210, 0.1)',
                                              color: 'primary.main',
                                              fontWeight: 600,
                                              fontSize: '0.7rem',
                                              height: 24,
                                              minWidth: 48
                                            }}
                                          />
                                        )}
                                      </Box>
                                    </Box>
                                  );
                                })}
                              </Box>
                            </Box>
                          );
                        });
                      })()}

                      <TextField
                        fullWidth
                        hiddenLabel
                        multiline
                        variant="filled"
                        size="small"
                        minRows={2}
                        value={typeof data.key_features === 'string' ? data.key_features : ''}
                        onChange={(e) => setData({ ...data, key_features: e.target.value })}
                        placeholder="Добавить/редактировать..."
                        sx={{ mt: 2 }}
                        InputProps={{ disableUnderline: true, sx: { borderRadius: 1.5, bgcolor: 'white', fontSize: '0.85rem' } }}
                      />
                    </Paper>

                    {/* 6. ИНТЕГРАЦИИ — список кликабельных пунктов */}
                    <Paper elevation={0} sx={{ gridColumn: '1 / -1', p: 3, bgcolor: 'white', borderRadius: 3, border: '1px solid', borderColor: 'divider' }}>
                      <Typography variant="h6" fontWeight={600} gutterBottom>
                        Интеграции
                      </Typography>
                      <Box display="flex" flexWrap="wrap" gap={1}>
                        {data._original?.client_integrations?.map((item, idx) => {
                          const issue = getIssueForItem('client_integrations', item.text);
                          const isSelected = selectedItem?.field === 'client_integrations' && selectedItem?.text === item.text;
                          return (
                            <Chip
                              key={idx}
                              label={item.text}
                              onClick={() => setSelectedItem({ field: 'client_integrations', text: item.text, source: item.source, issue })}
                              icon={issue ? (
                                issue.type === 'impossible' ? <ErrorIcon fontSize="small" /> :
                                  issue.type === 'contradictory' ? <SyncProblem fontSize="small" /> :
                                    <Warning fontSize="small" />
                              ) : undefined}
                              sx={{
                                cursor: 'pointer',
                                borderColor: isSelected ? 'primary.main' : undefined,
                                bgcolor: issue ? (issue.type === 'impossible' ? '#FFEBEE' : issue.type === 'contradictory' ? '#E3F2FD' : '#FFF8E1') : undefined,
                                '& .MuiChip-icon': {
                                  color: issue?.type === 'impossible' ? '#D32F2F' : issue?.type === 'contradictory' ? '#0288D1' : '#ED6C02'
                                }
                              }}
                              variant={isSelected ? 'filled' : 'outlined'}
                              color={isSelected ? 'primary' : 'default'}
                            />
                          );
                        })}
                      </Box>
                      <TextField
                        fullWidth
                        hiddenLabel
                        multiline
                        variant="filled"
                        size="small"
                        minRows={1}
                        value={data.client_integrations || ''}
                        onChange={(e) => setData({ ...data, client_integrations: e.target.value })}
                        placeholder="Добавить интеграции..."
                        sx={{ mt: 2 }}
                        InputProps={{ disableUnderline: true, sx: { borderRadius: 1.5, bgcolor: 'grey.50', fontSize: '0.85rem' } }}
                      />
                    </Paper>

                  </Box>
                </Container>
              </Box>

              {/* Правая часть: Боковая панель с цитатами из ТЗ */}
              <Box
                sx={{
                  flex: 1,
                  display: { xs: 'none', lg: 'block' },
                  position: 'sticky',
                  top: 80,
                  alignSelf: 'flex-start',
                  maxHeight: 'calc(100vh - 100px)',
                  overflow: 'auto',
                  minWidth: 350,
                  zIndex: 10
                }}
              >
                <Paper
                  elevation={0}
                  sx={{
                    p: 2.5,
                    bgcolor: '#F5F5F5',
                    borderRadius: 2,
                    border: '1px solid',
                    borderColor: 'divider'
                  }}
                >
                  <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 2, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Источник в ТЗ
                  </Typography>

                  {selectedItem && selectedItem.source ? (
                    <Box>
                      <Chip
                        label={selectedItem.field?.replace(/_/g, ' ') || 'пункт'}
                        size="small"
                        color="primary"
                        sx={{ mb: 1.5, textTransform: 'capitalize' }}
                      />
                      <Typography variant="body2" sx={{ mb: 1.5, fontWeight: 500 }}>
                        {selectedItem.text}
                      </Typography>
                      <Divider sx={{ mb: 1.5 }} />
                      <Paper
                        elevation={0}
                        sx={{
                          p: 2,
                          bgcolor: 'white',
                          borderRadius: 1.5,
                          border: '1px solid',
                          borderColor: 'divider'
                        }}
                      >
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                          Цитата из ТЗ:
                        </Typography>
                        <Typography
                          variant="body2"
                          sx={{
                            whiteSpace: 'pre-wrap',
                            fontFamily: 'monospace',
                            fontSize: '0.8rem',
                            lineHeight: 1.6,
                            color: 'text.primary',
                            bgcolor: '#FFFDE7',
                            p: 1.5,
                            borderRadius: 1,
                            borderLeft: '3px solid #FFC107'
                          }}
                        >
                          "{selectedItem.source}"
                        </Typography>
                      </Paper>
                      {/* Если есть issue для этого пункта */}
                      {selectedItem.issue && (
                        <Alert
                          severity={selectedItem.issue.type === 'impossible' ? 'error' : selectedItem.issue.type === 'contradictory' ? 'info' : 'warning'}
                          sx={{ mt: 2, borderRadius: 1.5 }}
                        >
                          <AlertTitle sx={{ fontWeight: 600 }}>
                            {selectedItem.issue.type === 'impossible' ? 'Нереализуемое' :
                              selectedItem.issue.type === 'contradictory' ? 'Противоречие' : 'Требует уточнения'}
                          </AlertTitle>
                          {selectedItem.issue.reason}
                        </Alert>
                      )}
                    </Box>
                  ) : (
                    <Typography variant="body2" color="text.disabled">
                      Кликните на пункт слева, чтобы увидеть исходный текст из ТЗ
                    </Typography>
                  )}
                </Paper>
              </Box>

            </Box>

            {/* ПРОДОЛЖАЕМ ОСТАЛЬНОЙ UI В ОБЫЧНОМ КОНТЕЙНЕРЕ ИЛИ ТОЖЕ ВНУТРИ? 
                Таблица сметы широкая, лучше оставить её как есть или тоже вписать в 900px?
                В запросе: "Ограничь ширину контента... для центрального блока".
                Таблицу можно оставить широкой, но для консистентности лучше тоже 900px.
            */}
            <Container maxWidth="lg" disableGutters sx={{ mb: 4 }}>

              {/* ТАБЛИЦА СМЕТЫ - новый компонент */}
              <BudgetMatrix
                stages={stages}
                setStages={setStages}
                roles={roles}
                setRoles={setRoles}
                budgetMatrix={budgetMatrix}
                setBudgetMatrix={setBudgetMatrix}
                userModified={userModified}
                setUserModified={setUserModified}
                suggestedHours={suggestedHours}
                onDeleteStage={handleDeleteStage}
                onDeleteRole={handleDeleteRole}
              />

              {/* Кнопка утверждения */}
              <Box display="flex" justifyContent="flex-end" mt={3}>
                <Button
                  variant="contained"
                  size="large"
                  onClick={handleApprove}
                  startIcon={<CheckCircle />}
                  sx={{ px: 5, py: 1.5 }}
                >
                  Утвердить и сгенерировать КП
                </Button>
              </Box>
            </Container>
          </Paper >
        )
        }

        {/* БЛОК 4: РЕЗУЛЬТАТ */}
        {
          status === "COMPLETED" && (
            <Paper elevation={0} sx={{ p: 4, bgcolor: '#E8F5E9', borderRadius: 4 }}>
              <Box display="flex" alignItems="center" mb={3}>
                <CheckCircle color="success" sx={{ fontSize: 48, mr: 2 }} />
                <Typography variant="h5" fontWeight={600}>
                  КП Успешно сгенерировано!
                </Typography>
              </Box>


              <Box sx={{ minHeight: 500 }}>
                {(() => {
                  // --- ГЕНЕРАЦИЯ ДАННЫХ ДЛЯ ШАБЛОНОВ ---
                  const totalBudget = Object.keys(budgetMatrix).reduce((sum, stage) => {
                    return sum + Object.keys(roles).reduce((s, role) => {
                      return s + (budgetMatrix[stage]?.[role] || 0) * roles[role];
                    }, 0);
                  }, 0);

                  // 1. Таблица сметы
                  let budgetTable = "| Этап | Роль | Часы | Ставка | Сумма |\n|---|---|---|---|---|\n";
                  Object.keys(budgetMatrix).forEach(stage => {
                    const stageRoles = budgetMatrix[stage] || {};
                    let hasRoles = false;
                    Object.keys(stageRoles).forEach(role => {
                      const hours = stageRoles[role];
                      if (hours > 0) {
                        hasRoles = true;
                        const rate = roles[role];
                        budgetTable += `| ${stage} | ${role} | ${hours} | ${rate} ₽ | ${hours * rate} ₽ |\n`;
                      }
                    });
                    // Если на этапе нет часов, можно добавить пустую строку или пропустить
                  });
                  budgetTable += `| **ИТОГО** | | | | **${totalBudget} ₽** |`;

                  // 2. Таблица этапов
                  let stagesTable = "| Этап | Описание |\n|---|---|\n";
                  stages.forEach(stage => {
                    // Можно добавить часы или просто список
                    const stageHours = Object.keys(roles).reduce((acc, r) => acc + (budgetMatrix[stage]?.[r] || 0), 0);
                    stagesTable += `| ${stage} | ${stageHours} ч. |\n`;
                  });

                  // 3. Таблица команды
                  let teamTable = "| Роль | Ставка |\n|---|---|\n";
                  Object.entries(roles).forEach(([role, rate]) => {
                    teamTable += `| ${role} | ${rate} ₽/час |\n`;
                  });

                  return (
                    <MarkdownEditor
                      value={finalDoc || ''}
                      onChange={setFinalDoc}
                      data={{
                        client_name: data?.client_name || '',
                        project_type: data?.project_type || '',
                        project_essence: data?.project_essence || '',
                        business_goals: data?.business_goals || '',
                        key_features: data?.key_features || '',
                        tech_stack: data?.tech_stack || '',
                        integrations: data?.client_integrations || '',
                        date: new Date().toLocaleDateString('ru-RU'),
                        // Calculated fields
                        total_budget: totalBudget,
                        budget_table: budgetTable,
                        stages_table: stagesTable,
                        team_table: teamTable,
                        timeline: 'По согласованию' // Placeholder
                      }}
                    />
                  );
                })()}
              </Box>

              <Box display="flex" gap={2} mt={3}>
                <Button
                  variant="contained"
                  size="large"
                  startIcon={<GetApp />}
                  onClick={handleDownload}
                  sx={{ px: 4 }}
                >
                  Скачать .docx
                </Button>

                <Button
                  variant="outlined"
                  size="large"
                  startIcon={<Refresh />}
                  onClick={() => window.location.reload()}
                >
                  Новый расчет
                </Button>
              </Box>
            </Paper>
          )
        }
      </Container >

      {/* МОДАЛКИ ДЛЯ ДОБАВЛЕНИЯ */}
      < Dialog open={openRoleDialog} onClose={() => setOpenRoleDialog(false)} maxWidth="xs" fullWidth >
        <DialogTitle sx={{ fontWeight: 600 }}>Добавить роль</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <TextField
            autoFocus
            margin="dense"
            label="Название роли"
            fullWidth
            value={newRoleName}
            onChange={(e) => setNewRoleName(e.target.value)}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label="Ставка (₽/час)"
            type="number"
            fullWidth
            value={newRoleRate}
            onChange={(e) => setNewRoleRate(e.target.value)}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button onClick={() => setOpenRoleDialog(false)}>Отмена</Button>
          <Button onClick={handleAddRole} variant="contained">Добавить</Button>
        </DialogActions>
      </Dialog >

      <Dialog open={openStageDialog} onClose={() => setOpenStageDialog(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 600 }}>Добавить этап</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <TextField
            autoFocus
            margin="dense"
            label="Название этапа"
            fullWidth
            value={newStageName}
            onChange={(e) => setNewStageName(e.target.value)}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button onClick={() => setOpenStageDialog(false)}>Отмена</Button>
          <Button onClick={handleAddStage} variant="contained">Добавить</Button>
        </DialogActions>
      </Dialog>
    </Box >
  );
}