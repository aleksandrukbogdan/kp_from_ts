
import React, { useState, useCallback, useMemo, useEffect } from 'react';
import {
    Box, Paper, TextField, Typography, IconButton, Tooltip, Divider,
    ToggleButton, ToggleButtonGroup, Select, MenuItem, FormControl,
    InputLabel, Snackbar, Alert, Chip
} from '@mui/material';
import {
    ContentCopy, FormatBold, FormatItalic, FormatListBulleted,
    FormatListNumbered, TableChart, Code, Title, Visibility,
    VisibilityOff, Edit, DragIndicator
} from '@mui/icons-material';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors } from '@dnd-kit/core';
import { arrayMove, SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { KP_TEMPLATES, getSectionsFromTemplate } from './KPTemplates';

// Сортируемая секция документа
const SortableSection = ({ id, title, content, onContentChange, isEditing }) => {
    const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
    };

    return (
        <Paper
            ref={setNodeRef}
            style={style}
            elevation={isDragging ? 4 : 0}
            sx={{
                p: 2,
                mb: 1.5,
                border: '1px solid',
                borderColor: isDragging ? 'primary.main' : 'divider',
                borderRadius: 2,
                bgcolor: isDragging ? 'primary.50' : 'white',
            }}
        >
            <Box display="flex" alignItems="center" gap={1} mb={1}>
                <IconButton
                    {...attributes}
                    {...listeners}
                    size="small"
                    sx={{ cursor: 'grab', color: 'text.secondary' }}
                >
                    <DragIndicator fontSize="small" />
                </IconButton>
                <Chip label={title} size="small" color="primary" variant="outlined" />
            </Box>
            {isEditing ? (
                <TextField
                    fullWidth
                    multiline
                    minRows={2}
                    value={content}
                    onChange={(e) => onContentChange(id, e.target.value)}
                    variant="outlined"
                    size="small"
                    sx={{ '& .MuiInputBase-root': { fontFamily: 'monospace', fontSize: '0.85rem' } }}
                />
            ) : (
                <Box sx={{ '& p': { m: 0 }, '& h1,h2,h3': { mt: 0 } }}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
                </Box>
            )}
        </Paper>
    );
};

// Основной компонент редактора
export default function MarkdownEditor({ value, onChange, data = {} }) {
    const [viewMode, setViewMode] = useState('split'); // 'edit', 'preview', 'split'
    const [selectedTemplate, setSelectedTemplate] = useState('standard');
    const [sections, setSections] = useState([]);
    const [useSections, setUseSections] = useState(false);
    const [snackbar, setSnackbar] = useState({ open: false, message: '' });

    // DnD сенсоры
    const sensors = useSensors(
        useSensor(PointerSensor),
        useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
    );

    // Вставка форматирования в текст
    const insertFormat = useCallback((format) => {
        const textarea = document.querySelector('#markdown-editor-textarea');
        if (!textarea) return;

        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const text = value;
        const selectedText = text.substring(start, end);

        let newText = '';
        let cursorOffset = 0;

        switch (format) {
            case 'bold':
                newText = text.substring(0, start) + `**${selectedText || 'текст'}**` + text.substring(end);
                cursorOffset = selectedText ? 0 : 7;
                break;
            case 'italic':
                newText = text.substring(0, start) + `*${selectedText || 'текст'}*` + text.substring(end);
                cursorOffset = selectedText ? 0 : 6;
                break;
            case 'h1':
                newText = text.substring(0, start) + `\n# ${selectedText || 'Заголовок'}\n` + text.substring(end);
                break;
            case 'h2':
                newText = text.substring(0, start) + `\n## ${selectedText || 'Подзаголовок'}\n` + text.substring(end);
                break;
            case 'ul':
                newText = text.substring(0, start) + `\n- ${selectedText || 'Пункт списка'}\n` + text.substring(end);
                break;
            case 'ol':
                newText = text.substring(0, start) + `\n1. ${selectedText || 'Пункт списка'}\n` + text.substring(end);
                break;
            case 'code':
                newText = text.substring(0, start) + `\`${selectedText || 'код'}\`` + text.substring(end);
                break;
            case 'table':
                newText = text.substring(0, start) + `\n| Колонка 1 | Колонка 2 |\n|-----------|-----------|\n| Данные | Данные |\n` + text.substring(end);
                break;
            default:
                return;
        }

        onChange(newText);
    }, [value, onChange]);

    // Копирование в буфер обмена
    const handleCopy = useCallback(async () => {
        try {
            await navigator.clipboard.writeText(value);
            setSnackbar({ open: true, message: 'Скопировано в буфер обмена!' });
        } catch (err) {
            setSnackbar({ open: true, message: 'Ошибка копирования' });
        }
    }, [value]);

    const handleTemplateChange = useCallback((templateId) => {
        setSelectedTemplate(templateId);
        const templateSections = getSectionsFromTemplate(templateId);

        // Заполняем секции данными
        const filledSections = templateSections.map(section => {
            let content = section.template;
            Object.entries(data).forEach(([key, val]) => {
                const placeholder = `{${key}}`;
                if (typeof val === 'string') {
                    // Escaping special characters for regex
                    content = content.replace(new RegExp(placeholder.replace(/[{}]/g, '\\$&'), 'g'), val);
                } else if (typeof val === 'number') {
                    content = content.replace(new RegExp(placeholder.replace(/[{}]/g, '\\$&'), 'g'), val);
                }
            });
            return { ...section, content };
        });

        setSections(filledSections);
        setUseSections(true);

        // Также обновляем общий текст
        const fullText = filledSections.map(s => s.content).join('\n');
        onChange(fullText);
    }, [data, onChange]);

    // Инициализация при первом рендере (если есть данные, но нет секций)
    useEffect(() => {
        if (!useSections && sections.length === 0 && data && Object.keys(data).length > 0) {
            handleTemplateChange(selectedTemplate);
        }
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // Обработка изменения секции
    const handleSectionChange = useCallback((sectionId, newContent) => {
        setSections(prev => {
            const updated = prev.map(s => s.id === sectionId ? { ...s, content: newContent } : s);
            // Обновляем общий текст
            const fullText = updated.map(s => s.content).join('\n');
            onChange(fullText);
            return updated;
        });
    }, [onChange]);

    // Drag and drop
    const handleDragEnd = useCallback((event) => {
        const { active, over } = event;
        if (active.id !== over.id) {
            setSections((items) => {
                const oldIndex = items.findIndex(i => i.id === active.id);
                const newIndex = items.findIndex(i => i.id === over.id);
                const newItems = arrayMove(items, oldIndex, newIndex);
                // Обновляем общий текст
                const fullText = newItems.map(s => s.content).join('\n');
                onChange(fullText);
                return newItems;
            });
        }
    }, [onChange]);

    // Markdown стили для preview
    const markdownStyles = useMemo(() => ({
        '& h1': { fontSize: '1.75rem', fontWeight: 700, mt: 3, mb: 2, color: 'text.primary' },
        '& h2': { fontSize: '1.4rem', fontWeight: 600, mt: 2.5, mb: 1.5, color: 'text.primary', borderBottom: '1px solid', borderColor: 'divider', pb: 0.5 },
        '& h3': { fontSize: '1.15rem', fontWeight: 600, mt: 2, mb: 1, color: 'text.secondary' },
        '& p': { mb: 1.5, lineHeight: 1.7 },
        '& ul, & ol': { pl: 3, mb: 1.5 },
        '& li': { mb: 0.5 },
        '& table': { width: '100%', borderCollapse: 'collapse', mb: 2 },
        '& th, & td': { border: '1px solid', borderColor: 'divider', p: 1, textAlign: 'left' },
        '& th': { bgcolor: 'grey.100', fontWeight: 600 },
        '& blockquote': { borderLeft: '4px solid', borderColor: 'primary.main', pl: 2, ml: 0, fontStyle: 'italic', color: 'text.secondary' },
        '& code': { bgcolor: 'grey.100', px: 0.5, borderRadius: 0.5, fontFamily: 'monospace', fontSize: '0.85em' },
        '& pre': { bgcolor: 'grey.900', color: 'white', p: 2, borderRadius: 1, overflow: 'auto' },
        '& hr': { border: 'none', borderTop: '2px solid', borderColor: 'divider', my: 3 },
    }), []);

    return (
        <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            {/* Toolbar */}
            <Paper
                elevation={0}
                sx={{
                    p: 1.5,
                    mb: 2,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 2,
                    flexWrap: 'wrap',
                    bgcolor: 'grey.50',
                    borderRadius: 2,
                }}
            >
                {/* View mode toggle */}
                <ToggleButtonGroup
                    value={viewMode}
                    exclusive
                    onChange={(e, v) => v && setViewMode(v)}
                    size="small"
                >
                    <ToggleButton value="edit">
                        <Tooltip title="Только редактор"><Edit fontSize="small" /></Tooltip>
                    </ToggleButton>
                    <ToggleButton value="split">
                        <Tooltip title="Редактор + Превью"><Visibility fontSize="small" /></Tooltip>
                    </ToggleButton>
                    <ToggleButton value="preview">
                        <Tooltip title="Только превью"><VisibilityOff fontSize="small" /></Tooltip>
                    </ToggleButton>
                </ToggleButtonGroup>

                <Divider orientation="vertical" flexItem />

                {/* Formatting buttons */}
                <Box display="flex" gap={0.5}>
                    <Tooltip title="Жирный (Ctrl+B)">
                        <IconButton size="small" onClick={() => insertFormat('bold')}><FormatBold fontSize="small" /></IconButton>
                    </Tooltip>
                    <Tooltip title="Курсив (Ctrl+I)">
                        <IconButton size="small" onClick={() => insertFormat('italic')}><FormatItalic fontSize="small" /></IconButton>
                    </Tooltip>
                    <Tooltip title="Заголовок H1">
                        <IconButton size="small" onClick={() => insertFormat('h1')}><Title fontSize="small" /></IconButton>
                    </Tooltip>
                    <Tooltip title="Маркированный список">
                        <IconButton size="small" onClick={() => insertFormat('ul')}><FormatListBulleted fontSize="small" /></IconButton>
                    </Tooltip>
                    <Tooltip title="Нумерованный список">
                        <IconButton size="small" onClick={() => insertFormat('ol')}><FormatListNumbered fontSize="small" /></IconButton>
                    </Tooltip>
                    <Tooltip title="Таблица">
                        <IconButton size="small" onClick={() => insertFormat('table')}><TableChart fontSize="small" /></IconButton>
                    </Tooltip>
                    <Tooltip title="Код">
                        <IconButton size="small" onClick={() => insertFormat('code')}><Code fontSize="small" /></IconButton>
                    </Tooltip>
                </Box>

                <Divider orientation="vertical" flexItem />

                {/* Template selector */}
                <FormControl size="small" sx={{ minWidth: 180 }}>
                    <InputLabel>Шаблон КП</InputLabel>
                    <Select
                        value={selectedTemplate}
                        label="Шаблон КП"
                        onChange={(e) => handleTemplateChange(e.target.value)}
                    >
                        {Object.values(KP_TEMPLATES).map(t => (
                            <MenuItem key={t.id} value={t.id}>
                                <Box>
                                    <Typography variant="body2">{t.name}</Typography>
                                    <Typography variant="caption" color="text.secondary">{t.description}</Typography>
                                </Box>
                            </MenuItem>
                        ))}
                    </Select>
                </FormControl>

                <Box flex={1} />

                {/* Copy button */}
                <Tooltip title="Копировать в буфер">
                    <IconButton onClick={handleCopy} color="primary">
                        <ContentCopy />
                    </IconButton>
                </Tooltip>
            </Paper>

            {/* Editor / Preview area */}
            <Box flex={1} display="flex" gap={2} minHeight={400}>
                {/* Editor pane */}
                {(viewMode === 'edit' || viewMode === 'split') && (
                    <Paper
                        elevation={0}
                        sx={{
                            flex: 1,
                            p: 2,
                            border: '1px solid',
                            borderColor: 'divider',
                            borderRadius: 2,
                            display: 'flex',
                            flexDirection: 'column',
                            overflow: 'hidden',
                        }}
                    >
                        <Typography variant="caption" color="text.secondary" sx={{ mb: 1 }}>
                            РЕДАКТОР {useSections && '(секции)'}
                        </Typography>

                        {useSections ? (
                            <Box sx={{ flex: 1, overflow: 'auto' }}>
                                <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                                    <SortableContext items={sections.map(s => s.id)} strategy={verticalListSortingStrategy}>
                                        {sections.map(section => (
                                            <SortableSection
                                                key={section.id}
                                                id={section.id}
                                                title={section.title}
                                                content={section.content}
                                                onContentChange={handleSectionChange}
                                                isEditing={true}
                                            />
                                        ))}
                                    </SortableContext>
                                </DndContext>
                            </Box>
                        ) : (
                            <TextField
                                id="markdown-editor-textarea"
                                fullWidth
                                multiline
                                value={value}
                                onChange={(e) => onChange(e.target.value)}
                                placeholder="Введите текст в формате Markdown..."
                                sx={{
                                    flex: 1,
                                    '& .MuiInputBase-root': {
                                        height: '100%',
                                        alignItems: 'flex-start',
                                        fontFamily: 'monospace',
                                        fontSize: '0.9rem',
                                        lineHeight: 1.6,
                                    },
                                    '& .MuiInputBase-input': {
                                        height: '100% !important',
                                        overflow: 'auto !important',
                                    },
                                }}
                                InputProps={{ disableUnderline: true }}
                                variant="standard"
                            />
                        )}
                    </Paper>
                )}

                {/* Preview pane */}
                {(viewMode === 'preview' || viewMode === 'split') && (
                    <Paper
                        elevation={0}
                        sx={{
                            flex: 1,
                            p: 3,
                            border: '1px solid',
                            borderColor: 'divider',
                            borderRadius: 2,
                            overflow: 'auto',
                            bgcolor: 'white',
                        }}
                    >
                        <Typography variant="caption" color="text.secondary" sx={{ mb: 2, display: 'block' }}>
                            ПРЕВЬЮ
                        </Typography>
                        <Box sx={markdownStyles}>
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                {value || '*Начните вводить текст...*'}
                            </ReactMarkdown>
                        </Box>
                    </Paper>
                )}
            </Box>

            {/* Snackbar */}
            <Snackbar
                open={snackbar.open}
                autoHideDuration={2000}
                onClose={() => setSnackbar({ ...snackbar, open: false })}
                anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
            >
                <Alert severity="success" variant="filled">{snackbar.message}</Alert>
            </Snackbar>
        </Box>
    );
}
