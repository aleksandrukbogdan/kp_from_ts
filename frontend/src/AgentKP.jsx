import React, { useState, useEffect } from 'react';
import {
  Container, Paper, Typography, Button, TextField,
  Box, CircularProgress, Table, TableBody, TableContainer,
  TableCell, TableHead, TableRow, IconButton, Chip,
  Dialog, DialogTitle, DialogContent, DialogActions,
  AppBar, Toolbar, Avatar, Menu, MenuItem, Divider
} from '@mui/material';
import {
  CloudUpload, CheckCircle, Add, Delete, Refresh, ArrowBack, Logout, Person, GetApp
} from '@mui/icons-material';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { config } from './config';

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
          // Преобразуем массивы в строки для удобного редактирования
          const formattedData = {
            ...raw,
            business_goals: formatDataToString(raw.business_goals),
            key_features: formatDataToString(raw.key_features),
            tech_stack: formatDataToString(raw.tech_stack),
          };
          setData(formattedData);

          // Инициализируем матрицу нулями, чтобы не было undefined
          const initialMatrix = {};
          stages.forEach(s => {
            initialMatrix[s] = {};
            Object.keys(roles).forEach(r => initialMatrix[s][r] = 0);
          });
          setBudgetMatrix(initialMatrix);
        }

        // Когда все готово
        if (state.status === "COMPLETED") {
          setFinalDoc(state.final_proposal);
          clearInterval(interval);
        }
      } catch (err) {
        console.error("Ошибка опроса:", err);
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
          <Paper elevation={0} sx={{ p: 4, borderRadius: 4 }}>
            <Typography variant="h5" gutterBottom fontWeight={600} sx={{ mb: 3 }}>
              📊 Проверка данных
            </Typography>

            <Box display="grid" gridTemplateColumns={{ xs: '1fr', md: '1fr 1fr' }} gap={3} mb={3}>
              <TextField
                label="Клиент"
                fullWidth
                variant="outlined"
                value={data.client_name || ''}
                onChange={(e) => setData({ ...data, client_name: e.target.value })}
              />
              <TextField
                label="Суть проекта"
                fullWidth
                multiline
                rows={3}
                variant="outlined"
                value={data.project_essence || ''}
                onChange={(e) => setData({ ...data, project_essence: e.target.value })}
              />
            </Box>

            <TextField
              label="Бизнес-задачи"
              fullWidth
              multiline
              rows={4}
              variant="outlined"
              value={data.business_goals || ''}
              onChange={(e) => setData({ ...data, business_goals: e.target.value })}
              sx={{ mb: 3 }}
            />

            <TextField
              label="Ключевой функционал"
              fullWidth
              multiline
              rows={6}
              variant="outlined"
              value={data.key_features || ''}
              onChange={(e) => setData({ ...data, key_features: e.target.value })}
              sx={{ mb: 3 }}
            />

            <TextField
              label="Стек и технологии"
              fullWidth
              multiline
              rows={2}
              variant="outlined"
              value={data.tech_stack || ''}
              onChange={(e) => setData({ ...data, tech_stack: e.target.value })}
              helperText="Если не указано в ТЗ, можно оставить как есть или дополнить вручную"
              sx={{ mb: 4 }}
            />

            {/* ТАБЛИЦА СМЕТЫ */}
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6" fontWeight={600}>Матрица трудозатрат</Typography>
              <Box>
                <Button
                  startIcon={<Add />}
                  onClick={() => setOpenStageDialog(true)}
                  sx={{ color: 'primary.main' }}
                >
                  Этап
                </Button>
                <Button
                  startIcon={<Add />}
                  onClick={() => setOpenRoleDialog(true)}
                  sx={{ color: 'primary.main' }}
                >
                  Роль
                </Button>
              </Box>
            </Box>

            <TableContainer sx={{ borderRadius: 2, border: '1px solid', borderColor: 'divider', mb: 4 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ minWidth: 150 }}>
                      <strong>Этапы работ</strong>
                    </TableCell>
                    {Object.keys(roles).map(role => (
                      <TableCell key={role} align="center" sx={{ minWidth: 120 }}>
                        <Box display="flex" flexDirection="column" alignItems="center">
                          <Box display="flex" alignItems="center" gap={0.5}>
                            <Typography variant="body2" fontWeight={600}>{role}</Typography>
                            <IconButton size="small" onClick={() => handleDeleteRole(role)} sx={{ color: 'text.secondary', p: 0.5 }}>
                              <Delete fontSize="small" />
                            </IconButton>
                          </Box>
                          <Typography variant="caption" color="text.secondary">
                            {roles[role].toLocaleString()} ₽/ч
                          </Typography>
                        </Box>
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {stages.map(stage => (
                    <TableRow key={stage} hover>
                      <TableCell component="th" scope="row" sx={{ fontWeight: 500 }}>
                        <Box display="flex" alignItems="center" justifyContent="space-between">
                          {stage}
                          <IconButton size="small" onClick={() => handleDeleteStage(stage)} sx={{ color: 'text.secondary', opacity: 0.5, '&:hover': { opacity: 1 } }}>
                            <Delete fontSize="small" />
                          </IconButton>
                        </Box>
                      </TableCell>
                      {Object.keys(roles).map(role => (
                        <TableCell key={role} align="center">
                          <TextField
                            type="number"
                            variant="standard"
                            InputProps={{
                              disableUnderline: true,
                              inputProps: { style: { textAlign: 'center' }, min: 0 }
                            }}
                            sx={{
                              width: 60,
                              '& input': { p: 1, borderRadius: 1, bgcolor: 'background.default' }
                            }}
                            value={budgetMatrix[stage]?.[role] || 0}
                            onChange={(e) => handleHourChange(stage, role, e.target.value)}
                          />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            {/* Итоговая смета */}
            <Paper
              variant="outlined"
              sx={{
                p: 3,
                bgcolor: '#FFF0E0',
                borderRadius: 3,
                borderColor: 'primary.light',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 2,
              }}
            >
              <Box>
                <Typography variant="h6" color="text.primary">
                  Итоговая смета:
                </Typography>
                <Typography variant="h4" color="primary.main" fontWeight="bold">
                  {calculateTotal().toLocaleString('ru-RU')} ₽
                </Typography>
              </Box>
              <Button
                variant="contained"
                size="large"
                onClick={handleApprove}
                startIcon={<CheckCircle />}
                sx={{ px: 5, py: 1.5 }}
              >
                Утвердить КП
              </Button>
            </Paper>
          </Paper>
        )}

        {/* БЛОК 4: РЕЗУЛЬТАТ */}
        {status === "COMPLETED" && (
          <Paper elevation={0} sx={{ p: 4, bgcolor: '#E8F5E9', borderRadius: 4 }}>
            <Box display="flex" alignItems="center" mb={3}>
              <CheckCircle color="success" sx={{ fontSize: 48, mr: 2 }} />
              <Typography variant="h5" fontWeight={600}>
                КП Успешно сгенерировано!
              </Typography>
            </Box>

            <Paper
              elevation={0}
              variant="outlined"
              sx={{
                p: 3,
                borderRadius: 2,
                bgcolor: 'white',
              }}
            >
              <TextField
                fullWidth
                multiline
                minRows={10}
                maxRows={30}
                variant="outlined"
                value={finalDoc || ''}
                onChange={(e) => setFinalDoc(e.target.value)}
                sx={{ mb: 2 }}
              />
            </Paper>

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
        )}
      </Container>

      {/* МОДАЛКИ ДЛЯ ДОБАВЛЕНИЯ */}
      <Dialog open={openRoleDialog} onClose={() => setOpenRoleDialog(false)} maxWidth="xs" fullWidth>
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
      </Dialog>

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
    </Box>
  );
}