// Заглушка данных для поиска
const database = [
    "Буст аккаунтов Dota 2",
    "Продажа золота WoW",
    "Аккаунты Brawl Stars",
    "Установка Windows 10/11",
    "Сборка ПК под заказ",
    "Накрутка подписчиков Twitch",
    "Донат в игры (Genshin, Mobile Legends)",
    "Обучение программированию Python"
];

const searchInput = document.getElementById('search-input');
const suggestionsList = document.getElementById('search-suggestions');

searchInput.addEventListener('input', (e) => {
    const value = e.target.value.toLowerCase();
    suggestionsList.innerHTML = '';

    if (value.length < 1) {
        suggestionsList.style.display = 'none';
        return;
    }

    const filtered = database.filter(item =>
        item.toLowerCase().includes(value)
    );

    if (filtered.length > 0) {
        filtered.forEach(item => {
            const div = document.createElement('div');
            div.className = 'suggestion-item';
            div.textContent = item;
            div.onclick = () => {
                searchInput.value = item;
                suggestionsList.style.display = 'none';
            };
            suggestionsList.appendChild(div);
        });
        suggestionsList.style.display = 'block';
    } else {
        suggestionsList.style.display = 'none';
    }
});

// Закрытие поиска при клике вне его
document.addEventListener('click', (e) => {
    if (!searchInput.contains(e.target) && !suggestionsList.contains(e.target)) {
        suggestionsList.style.display = 'none';
    }
});
