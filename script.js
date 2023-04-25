// script.js



document.addEventListener("DOMContentLoaded", () => {
    displayRandomQuote(); 
});


function displayRandomQuote() {
    const randomIndex = Math.floor(Math.random() * quotes.length);
    const quote = quotes[randomIndex];
    const quoteElement = document.getElementById("quote");
    const quoteAuthorElement = document.getElementById("quote_author");

    quoteElement.textContent = quote.text;
    quoteAuthorElement.textContent = quote.author;
}


const quotes = [
{
    text: "The only way to do great work is to love what you do.",
    author: "Steve Jobs"
},
{
    text: "It does not matter how slowly you go as long as you do not stop.",
    author: "Confucius"
},
{
    text: "Success is not final, failure is not fatal: it is the courage to continue that counts.",
    author: "Winston Churchill"
},
{
    text: "The best way to predict the future is to invent it.",
    author: "Alan Kay"
},
{
    text: "Life is 10% what happens to you and 90% how you react to it.",
    author: "Charles R. Swindoll"
},
{
    text: "Believe you can and you're halfway there.",
    author: "Theodore Roosevelt"
},
{
    text: "You miss 100% of the shots you don't take.",
    author: "Wayne Gretzky"
},
{
    text: "The greatest glory in living lies not in never falling, but in rising every time we fall.",
    author: "Nelson Mandela"
},
{
    text: "The only limit to our realization of tomorrow will be our doubts of today.",
    author: "Franklin D. Roosevelt"
},
{
    text: "Don't judge each day by the harvest you reap but by the seeds that you plant.",
    author: "Robert Louis Stevenson"
},
{
    text: "It was the best of times, it was the worst of times, it was the age of wisdom, it was the age of foolishness...",
    author: "A Tale of Two Cities by Charles Dickens"
},
{
    text: "Call me Ishmael.",
    author: "Moby Dick by Herman Melville"
},
{
    text: "All happy families are alike; each unhappy family is unhappy in its own way.",
    author: "Anna Karenina by Leo Tolstoy"
},
{
    text: "So we beat on, boats against the current, borne back ceaselessly into the past.",
    author: "The Great Gatsby by F. Scott Fitzgerald"
},
{
    text: "It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife.",
    author: "Pride and Prejudice by Jane Austen"
},
{
    text: "In a hole in the ground there lived a hobbit.",
    author: "The Hobbit by J.R.R. Tolkien"
},
{
    text: "To be yourself in a world that is constantly trying to make you something else is the greatest accomplishment.",
    author: "Self-Reliance by Ralph Waldo Emerson"
},
{
    text: "I have nothing to offer but blood, toil, tears and sweat.",
    author: "The Second World War by Winston Churchill"
},
{
    text: "Whenever you feel like criticizing any one, just remember that all the people in this world haven't had the advantages that you've had.",
    author: "The Great Gatsby by F. Scott Fitzgerald"
},
{
    text: "All that is gold does not glitter, Not all those who wander are lost.",
    author: "The Fellowship of the Ring by J.R.R. Tolkien"
},
{
    text: "It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife.",
    author: "Pride and Prejudice by Jane Austen"
},
{
    text: "All happy families are alike; each unhappy family is unhappy in its own way.",
    author: "Anna Karenina by Leo Tolstoy"
},
{
    text: "It was the best of times, it was the worst of times, it was the age of wisdom, it was the age of foolishness...",
    author: "A Tale of Two Cities by Charles Dickens"
},
{
    text: "To be yourself in a world that is constantly trying to make you something else is the greatest accomplishment.",
    author: "Self-Reliance by Ralph Waldo Emerson"
},
{
    text: "All that is gold does not glitter, Not all those who wander are lost.",
    author: "The Fellowship of the Ring by J.R.R. Tolkien"
},
{
    text: "I have nothing to offer but blood, toil, tears, and sweat.",
    author: "The Second World War by Winston Churchill"
},
{
    text: "Whenever you feel like criticizing any one, just remember that all the people in this world haven't had the advantages that you've had.",
    author: "The Great Gatsby by F. Scott Fitzgerald"
},
{
    text: "In a hole in the ground there lived a hobbit.",
    author: "The Hobbit by J.R.R. Tolkien"
},
{
    text: "Call me Ishmael.",
    author: "Moby Dick by Herman Melville"
},
{
    text: "So we beat on, boats against the current, borne back ceaselessly into the past.",
    author: "The Great Gatsby by F. Scott Fitzgerald"
},
{
    text: "Two roads diverged in a wood, and I— I took the one less traveled by, And that has made all the difference.",
    author: "The Road Not Taken by Robert Frost"
},
{
    text: "It matters not what someone is born, but what they grow to be.",
    author: "Harry Potter and the Goblet of Fire by J.K. Rowling"
},
{
    text: "The only thing we have to fear is fear itself.",
    author: "First Inaugural Address by Franklin D. Roosevelt"
},
{
    text: "I took a deep breath and listened to the old brag of my heart. I am, I am, I am.",
    author: "The Bell Jar by Sylvia Plath"
},
{
    text: "Do not go gentle into that good night. Rage, rage against the dying of the light.",
    author: "Do Not Go Gentle Into That Good Night by Dylan Thomas"
},
{
    text: "There is no greater agony than bearing an untold story inside you.",
    author: "I Know Why the Caged Bird Sings by Maya Angelou"
},
{
    text: "Not all of us can do great things. But we can do small things with great love.",
    author: "A Simple Path by Mother Teresa"
},
{
    text: "The future belongs to those who believe in the beauty of their dreams.",
    author: "Eleanor Roosevelt"
},
{
    text: "Ask not what your country can do for you; ask what you can do for your country.",
    author: "Inaugural Address by John F. Kennedy"
},
{
    text: "You can't stay in your corner of the Forest waiting for others to come to you. You have to go to them sometimes.",
    author: "Winnie-the-Pooh by A.A. Milne"
},
{
    text: "There is no friend as loyal as a book.",
    author: "Ernest Hemingway"
},
{
    text: "If you don't stand for something, you will fall for anything.",
    author: "Malcolm X"
},
{
    text: "The journey of a thousand miles begins with a single step.",
    author: "Tao Te Ching by Lao Tzu"
},
{
    text: "To be yourself in a world that is constantly trying to make you something else is the greatest accomplishment.",
    author: "Ralph Waldo Emerson"
},
{
    text: "The only way to do great work is to love what you do.",
    author: "Steve Jobs"
},
{
    text: "We accept the love we think we deserve.",
    author: "The Perks of Being a Wallflower by Stephen Chbosky"
},
{
    text: "And, when you want something, all the universe conspires in helping you to achieve it.",
    author: "The Alchemist by Paulo Coelho"
},
{
    text: "In three words I can sum up everything I've learned about life: it goes on.",
    author: "Robert Frost"
},
{
    text: "It does not do to dwell on dreams and forget to live.",
    author: "Harry Potter and the Philosopher's Stone by J.K. Rowling"
},
{
    text: "No one can make you feel inferior without your consent.",
    author: "Eleanor Roosevelt"
},
{
    text: "Life isn't about finding yourself. Life is about creating yourself.",
    author: "George Bernard Shaw"
},
{
    text: "Success is not final, failure is not fatal: it is the courage to continue that counts.",
    author: "Winston Churchill"
},
{
    text: "The only thing necessary for the triumph of evil is for good men to do nothing.",
    author: "Edmund Burke"
},
{
    text: "To succeed in life, you need two things: ignorance and confidence.",
    author: "Mark Twain"
},
{
    text: "What lies behind us and what lies before us are tiny matters compared to what lies within us.",
    author: "Ralph Waldo Emerson"
},
{
    text: "Twenty years from now you will be more disappointed by the things that you didn't do than by the ones you did do.",
    author: "H. Jackson Brown Jr."
},
{
    text: "The only way to get through life is to laugh your way through it. You either have to laugh or cry. I prefer to laugh. Crying gives me a headache.",
    author: "Marjorie Pay Hinckley"
},
{
    text: "The secret of getting ahead is getting started.",
    author: "Mark Twain"
},
{
    text: "You miss 100% of the shots you don't take.",
    author: "Wayne Gretzky"
},

{
text: "He had never cried so much in his life, as if the tears were an ocean that could never be filled.",
author: "The Empty Sea by Jane Simmons"
},

{
text: "Her laughter, once the sun in his life, now echoed through the halls like a mournful ghost.",
author: "Haunting Melodies by John Harrison"
},

{
text: "He held her hand tightly, whispering apologies for all the times he had taken her love for granted.",
author: "Regretful Tides by Emily Williams"
},

{
text: "She stood at the edge of the cliff, watching the waves crash below, knowing that the sea could never wash away her pain.",
author: "Abyss of Sorrow by Alice Green"
},

{
text: "As the train pulled away from the station, she realized that leaving him behind was like tearing a piece of her soul away.",
author: "Departures by Peter Thompson"
},

{
text: "He stared at the empty chair, once her favorite spot, now a glaring reminder of her absence.",
author: "Silent Echoes by Samuel Cooper"
},

{
text: "Her words pierced his heart like a dagger, and he knew that the love they once shared had been lost forever.",
author: "Broken Hearts and Bitter Tears by Catherine Taylor"
},

{
text: "It was in the darkest corner of his heart that he stored his love for her, never to be seen again.",
author: "Secret Shadows by Sarah Reynolds"
},

{
text: "As the last petal fell from the rose, so too did her hope for their love ever blooming again.",
author: "A Withered Love by Michael Brown"
},

{
text: "She looked at the life they had built together, now crumbling like sandcastles in the wind.",
author: "Fading Dreams by Rachel Adams"
},

{
text: "He felt like a broken record, repeating the same mistakes and losing her love with each passing day.",
author: "A Symphony of Regrets by Daniel Walker"
},

{
text: "He watched as the leaves fell from the tree, each one a symbol of the love that had fallen from his life.",
author: "Autumn's Descent by Jessica King"
},

{
text: "Her eyes, once filled with love and warmth, now held only the cold reflection of a stranger.",
author: "The Icy Divide by James Turner"
},

{
text: "As the snowflakes melted on her cheeks, they became indistinguishable from the tears that flowed.",
author: "Winter's Heartache by Lauren Moore"
},

{
text: "The pain in his heart was like a thousand needles, each one a reminder of the love he had lost.",
author: "A Piercing Sorrow by Christopher Davis"
},

{
text: "He longed for the warmth of her embrace, knowing that it was now as unreachable as the stars above.",
author: "Celestial Longing by Olivia Lewis"
},

{
text: "The fire that once burned brightly between them had been extinguished, leaving only cold ashes and bitter memories.",
author: "Ashes of Love by William Morgan"
},

{
text: "She whispered his name into the night, knowing that the wind would carry it away like her love.",
author: "A Distant Memory by Karen Evans"
},
    // 他の名言と引用元を追加
];
