/*
 * Edit homepage content in this file.
 * The intro section still uses bodyHtml.
 * The sections below use row-based structured data so you can add entries without touching both HTML files.
 */

(() => {
    const t = (en, ja = en) => ({ en, ja });

    const joinNames = (names) => {
        if (names.length <= 1) {
            return names[0] || "";
        }

        if (names.length === 2) {
            return `${names[0]} and ${names[1]}`;
        }

        return `${names.slice(0, -1).join(", ")}, and ${names[names.length - 1]}`;
    };

    const link = (href, label = t("URL")) => ({ type: "link", href, label });
    const bold = (content) => ({ type: "bold", content });
    const italic = (content) => ({ type: "italic", content });
    const tag = (tagName, className, content) => ({ type: "tag", tagName, className, content });
    const seq = (...parts) => parts.flat().filter((part) => part !== "" && part != null);
    const paren = (content) => seq("(", content, ")");
    const bracket = (content) => seq("[", content, "]");
    const urlPart = (href) => (href ? paren(link(href, t("URL"))) : "");
    const doiPart = (href) => paren(link(href, t("DOI")));
    const pdfPart = (href) => paren(link(href, t("PDF")));
    const arxivPart = (id) => seq(`arXiv: ${id} `, urlPart(`https://arxiv.org/abs/${id}`));
    const leanPart = (href) => seq("Lean4 ", urlPart(href));
    const withPeople = (...names) => t(` (with ${joinNames(names)})`, `（with ${joinNames(names)}）`);
    const categoryTitle = (label) => tag("span", "category-title", label);

    const item = (content, extra = {}) => ({ ...extra, content });
    const nestedItem = (content, children = [], extra = {}) => ({ ...extra, content, children });
    const datedItem = (date, content, extra = {}) => item(seq(`${date}: `, content), extra);

    const paperEntry = ({ title, people = [], suffix = "", details = [] }) =>
        nestedItem(
            seq(italic(title), people.length ? withPeople(...people) : "", suffix),
            details.map((detail) => item(detail))
        );

    const paperCategory = (label, entries = []) => nestedItem(categoryTitle(label), entries);

    const talk = ({ date, event, eventUrl, venue, subject, venueSuffix = "", venueExtras = [] }) =>
        datedItem(
            date,
            seq(
                bold(event),
                eventUrl ? seq(" ", urlPart(eventUrl)) : "",
                ", ",
                venue,
                venueSuffix,
                venueExtras.length ? seq(" ", ...venueExtras) : "",
                ", ",
                italic(subject)
            )
        );

    const organizeEvent = ({ date, title, url, venue }) =>
        datedItem(date, seq(title, url ? seq(" ", urlPart(url)) : "", ", ", venue));

    const groupedSection = (label, children) => nestedItem(label, children);

    const linkRow = ({ name, url, suffix = "" }) => item(seq(name, url ? seq(" ", urlPart(url)) : "", suffix));

    const introBody = t(
        `
            <p>Position: Institute of Science Tokyo (JSPS PD)</p>
            <p>Expertise: Arithmetic Geometry, Anabelian Geometry</p>
            <p>Email: n.yamaguchi(at)mail.dendai.ac.jp</p>
            <p>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <s>yamaguchi.n.ac(at)m.titech.ac.jp</s></p>
            <p>
                ORCID:
                <a href="https://orcid.org/0000-0002-0347-2746" target="_blank">0000-0002-0347-2746</a>
            </p>
            <p>
                Researchmap ID:
                <a href="https://researchmap.jp/NaganoriYamaguchi" target="_blank">R000054174</a>
            </p>
            <p>
                ArXiv:
                <a
                    href="https://arxiv.org/search/?query=Naganori+Yamaguchi&searchtype=all&abstracts=show&order=-announced_date_first&size=50"
                    target="_blank"
                >URL</a>
            </p>
            <p>My bookshelf: <a href="https://booklog.jp/users/naganori1995" target="_blank">URL</a></p>
        `,
        `
            <p>現職：東京科学大学（旧東京工業大学）理学院 数学系 日本学術振興会特別研究員 PD</p>
            <p>専門分野：数論幾何学、遠アーベル幾何学</p>
            <p>メール: n.yamaguchi(at)mail.dendai.ac.jp</p>
            <p>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <s>yamaguchi.n.ac(at)m.titech.ac.jp</s></p>
            <p>
                ORCID:
                <a href="https://orcid.org/0000-0002-0347-2746" target="_blank">0000-0002-0347-2746</a>
            </p>
            <p>
                Researchmap ID:
                <a href="https://researchmap.jp/NaganoriYamaguchi" target="_blank">R000054174</a>
            </p>
            <p>
                ArXiv:
                <a
                    href="https://arxiv.org/search/?query=Naganori+Yamaguchi&searchtype=all&abstracts=show&order=-announced_date_first&size=50"
                    target="_blank"
                >URL</a>
            </p>
            <p>本棚: <a href="https://booklog.jp/users/naganori1995" target="_blank">URL</a></p>
        `
    );

    const paperGroups = [
        {
            label: t("Refereed Journal Articles:", "学術論文（査読有）:"),
            entries: [
                {
                    title: "The geometrically m-step solvable Grothendieck conjecture for affine hyperbolic curves over finitely generated fields",
                    details: [
                        seq(
                            "Journal of the London Mathematical Society, Volume 109, issue 5, May 2024, e12912. ",
                            doiPart("https://doi.org/10.1112/jlms.12912"),
                            ", ",
                            arxivPart("2302.09253")
                        )
                    ]
                },
                {
                    title: "The geometrically m-step solvable Grothendieck conjecture for genus 0 curves over finitely generated fields",
                    details: [
                        seq(
                            "Journal of Algebra, Volume 629, September 2023, Pages 191-226. ",
                            doiPart("https://doi.org/10.1016/j.jalgebra.2023.01.028"),
                            ", ",
                            arxivPart("2010.00290")
                        )
                    ]
                }
            ]
        },
        {
            label: t("Refereed Proceedings:", "プロシーディング（査読有）:"),
            entries: [
                {
                    title: "Center-freeness of finite-step solvable groups arising from anabelian geometry",
                    details: [seq(arxivPart("2601.07112"), ", ", leanPart("https://github.com/n-yamaguchi-0729/Yama2026"))]
                },
                {
                    title: "A survey of known results on the m-step solvable anabelian geometry for hyperbolic curves",
                    details: [
                        seq(
                            t("RIMS Kokyuroku Bessatsu (Forthcoming)", "数理解析研究所講究録別冊に掲載予定"),
                            ", ",
                            arxivPart("2204.08008")
                        )
                    ]
                }
            ]
        },
        {
            label: t("Refereed Survey Articles:", "解説・総説（査読有）:"),
            hidden: true,
            entries: []
        },
        {
            label: t("Preprints:", "プレプリント:"),
            entries: [
                {
                    title: "Triviality of Étale Fundamental groups of arithmetic varieties",
                    people: ["Ryoji Shimizu"],
                    details: [t("In preparation", "準備中")]
                },
                {
                    title: "The finite-step pro-solvable analogue of Fenchel's conjecture and anabelian geometry for stacky curves",
                    people: ["Benjamin Collas", "Séverin Philip"],
                    details: [t("In preparation", "準備中")]
                },
                {
                    title: "Étale fundamental groups of smooth arithmetic surfaces and the Grothendieck conjecture",
                    people: ["Ryoji Shimizu"],
                    details: [arxivPart("2511.06725")]
                },
                {
                    title: "Symmetries of spaces and numbers -- anabelian geometry",
                    people: ["Benjamin Collas", "Takahiro Murotani"],
                    details: [arxivPart("2508.01588")]
                },
                {
                    title: "A refined version of the geometrically m-step solvable Grothendieck conjecture for genus 0 curves over finitely generated fields",
                    details: [arxivPart("2407.09906")]
                }
            ]
        }
    ];

    const noteEntries = [
        {
            title: "Notes from “Atelier de Géométrie Arithmétique” – Étale homotopy theory and applications",
            people: ["Brieuc Lair", "Drimik Roy-Chowdhury"],
            suffix: seq(" ", pdfPart("https://ahgt.math.cnrs.fr/assets/pdf/AGA25-etale%20homotopy%20type%20-%20Notes.pdf"))
        },
        {
            title: "Notes from “Atelier de Géométrie Arithmétique” – Spaces and perfectoids",
            people: ["E. Caeiro", "A. Klughertz", "S. Philip"],
            suffix: seq(" ", pdfPart("https://ahgt.math.cnrs.fr/assets/pdf/AGA24%20-%20Spaces%20and%20perfectoids%20-%20Notes.pdf"))
        },
        {
            title: "遠アーベル幾何学におけるm階可解グロタンディーク予想について",
            suffix: seq(" ", pdfPart("https://www.math.sci.hokudai.ac.jp/~wakate/mcyr/2023/pdf/yamaguchi_naganori.pdf"))
        }
    ];

    const paperItems = paperGroups
        .filter(({ hidden }) => !hidden)
        .map(({ label, entries }) =>
            paperCategory(
                label,
                entries.map((entry) => paperEntry(entry))
            )
        );

    const noteItems = noteEntries.map((entry) => paperEntry(entry));

    const talkRows = [
        {
            date: "2025/11/26",
            event: t("KAIST Number Theory Seminar"),
            eventUrl: "https://sites.google.com/site/wansukimmaths/kants-kaist-number-theory-seminar#h.h7y8lhmej47y",
            venue: t("KAIST", "韓国科学技術院（KAIST）"),
            subject: "The anabelian geometry of arithmetic surfaces (Joint work with R. Shimizu)"
        },
        {
            date: "2025/11/22",
            event: t(
                "東京科学大学整数論研究集会 (Prof. Yuichiro Taguchi's 60th birthday)",
                "東京科学大学整数論研究集会（田口雄一郎教授還暦研究集会）"
            ),
            venue: t("Institute of Science Tokyo", "東京科学大学"),
            subject: "ノイキルヒ・内田の定理から見る遠アーベル幾何学"
        },
        {
            date: "2025/09/03",
            event: t("Anabelian Geometry in Yokohama 2025"),
            eventUrl: t(
                "https://sites.google.com/view/ag-in-yokohama-2025-en/home",
                "https://sites.google.com/view/ag-in-yokohama-2025-jp/home"
            ),
            venue: t("Kanagawa University", "神奈川大学"),
            subject: "The anabelian geometry of arithmetic surfaces (Joint work with R. Shimizu)"
        },
        {
            date: "2025/03/31",
            event: t("Spring seminar on Arithmetic Galois theory in Toyonaka 2025"),
            eventUrl: "http://www4.math.sci.osaka-u.ac.jp/~nakamura/ArithmeticDay2025/",
            venue: t("Osaka University", "大阪大学"),
            subject: "Finite Step Solvable Aspects of Anabelian Geometry"
        },
        {
            date: "2024/11/23",
            event: t("北大数論セミナー"),
            eventUrl: "https://www2.sci.hokudai.ac.jp/dept/math/event/12431",
            venue: t("Hokkaido University", "北海道大学"),
            subject: "The Finite-Step Solvability of Anabelian Geometry"
        },
        {
            date: "2024/10/25",
            event: t("九州代数学セミナー"),
            eventUrl: "https://www2.math.kyushu-u.ac.jp/~alg-seminar/",
            venue: t("Kyushu University", "九州大学"),
            subject: "Anabelian geometry and m-step solvable reconstruction"
        },
        {
            date: "2024/03/12",
            event: t("Anabelian Geometry in Tokyo 2024"),
            eventUrl: t(
                "https://sites.google.com/view/ag-in-tokyo-2024-en/home",
                "https://sites.google.com/view/ag-in-tokyo-2024-jp/home"
            ),
            venue: t("Tokyo Institute of Technology", "東京工業大学"),
            subject: "The m-step solvable reconstruction for the Grothendieck conjecture in Anabelian Geometry"
        },
        {
            date: "2024/02/15",
            event: t("MathSci Freshman Seminar 2024", "第7回数理新人セミナー"),
            eventUrl: "https://sites.google.com/view/math-graduate/MATHSCI-FRESHMAN-SEMINAR/2024",
            venue: t("Nagoya University", "名古屋大学"),
            subject: "Recent developments for m-step solvable Anabelian Geometry"
        },
        {
            date: "2023/07/14",
            event: t("22nd Hiroshima-Sendai Workshop on Number Theory", "第22回広島仙台整数論集会"),
            eventUrl: "https://math0.pm.tokushima-u.ac.jp/~hiroki/hiroshima23.html",
            venue: t("Hiroshima University", "広島大学"),
            subject: "New developments in anabelian geometry by using m-step reconstruction"
        },
        {
            date: "2023/04/17",
            event: "Arithmetic & Homotopic Galois Theory seminar of the International Research Network",
            eventUrl: "https://ahgt.math.cnrs.fr/seminar/",
            venue: t("RIMS, Kyoto University", "京都大学数理解析研究所"),
            venueSuffix: t(" (Invited Talk)", "（招待講演）"),
            subject: "Anabelian geometry and m-step reconstruction"
        },
        {
            date: "2023/03/28",
            event: t("Low Dimensional Topology and Number Theory XIV"),
            eventUrl: "https://www2.math.kyushu-u.ac.jp/~morisita/",
            venue: t("Kyushu University", "九州大学"),
            venueSuffix: t(" (Invited Talk)", "（招待講演）"),
            subject: "On the development of anabelian geometry using the maximal geometrically m-step solvable quotient of arithmetic fundamental groups"
        },
        {
            date: "2023/03/08",
            event: t("The 19th Mathematics Conference for Young Researchers", "第19回数学総合若手研究集会"),
            eventUrl: t(
                "https://www.math.sci.hokudai.ac.jp/~wakate/mcyr/2023/en/index.html",
                "https://www.math.sci.hokudai.ac.jp/~wakate/mcyr/2023/ja/index.html"
            ),
            venue: t("Hokkaido University", "北海道大学"),
            venueExtras: [
                seq(
                    t("(Technical Report: ", "（テクニカルレポート: "),
                    link("https://www.math.sci.hokudai.ac.jp/~wakate/mcyr/2023/pdf/yamaguchi_naganori.pdf", t("URL")),
                    t(")", "）")
                )
            ],
            subject: "遠アーベル幾何学におけるm階可解グロタンディーク予想について"
        },
        {
            date: "2021/12/07",
            event: "The Japan Europe Number Theory Exchange Seminar",
            eventUrl: "https://sites.google.com/view/jente-seminar/home",
            venue: t("Online", "Online 開催"),
            venueSuffix: t(" (Invited Talk)", "（招待講演）"),
            subject: "The m-step solvable anabelian geometry for hyperbolic curves over finitely generated fields"
        },
        {
            date: "2020/12/02",
            event: t("Algebraic Number Theory and Related Topics 2020", "代数的整数論とその周辺2020"),
            eventUrl: "https://web.archive.org/web/20201117233036/http://ntw.sci.u-toyama.ac.jp/rimsant2020/",
            venue: t("RIMS, Kyoto University", "京都大学数理解析研究所"),
            subject: "種数0の曲線における導来商版Grothendieck予想について"
        },
        {
            date: "2020/09/09",
            event: t("19th Sendai-Hiroshima Number Theory Conference", "第19回仙台広島整数論集会"),
            eventUrl: "https://math0.pm.tokushima-u.ac.jp/~hiroki/hiroshima20.html",
            venue: t("Tohoku University", "東北大学"),
            subject: "The m-step solvable Grothendieck conjecture for genus 0 curves over finitely generated fields"
        },
        {
            date: "2020/08/19",
            event: "2nd Kyoto-Hefei Workshop on Arithmetic Geometry 2020",
            eventUrl: "https://www.kurims.kyoto-u.ac.jp/~yuyang/confer/Kyoto-Hefei-2nd.html",
            venue: t("Online", "Online 開催"),
            venueSuffix: t(" (Invited Talk)", "（招待講演）"),
            subject: "The m-step solvable Grothendieck conjecture for genus 0 curves over finitely generated fields"
        },
        {
            date: "2020/08/11",
            event: t("Kyushu Algebraic Number Theory 2020", "九州代数的整数論2020"),
            eventUrl: "https://sites.google.com/view/kant2020sonzoom/",
            venue: t("Kyushu University", "九州大学"),
            subject: "The m-step solvable Grothendieck conjecture for genus 0 curves over finitely generated fields"
        }
    ];

    const talkItems = talkRows.map((row) => talk(row));

    const careerRows = [
        {
            date: "2024/09/05 - 2025/03/31",
            description: t(
                'Tokyo Denki University Part-time Teacher "Calculus II (1EJ・EH・ES)"',
                "東京電機大学 非常勤講師 微分積分学および演習 II（1EJ・EH・ES）"
            )
        },
        {
            date: "2023/09/05 - 2024/03/31",
            description: t(
                'Tokyo Denki University Part-time Teacher "Calculus II (1EJ・EH・ES)"',
                "東京電機大学 非常勤講師 微分積分学および演習 II（1EJ・EH・ES）"
            )
        },
        {
            date: "2023/04/01 - 2026/03/31",
            description: seq(
                t("Japan Society for the Promotion of Science Research Fellow PD", "日本学術振興会特別研究員 PD"),
                " ",
                urlPart("https://www.jsps.go.jp/file/storage/j-pd/data/list_of_recruits/R5_PD_saiyou.pdf#page=12")
            )
        },
        {
            date: "2021/04/01 - 2023/03/31",
            description: seq(
                t("Japan Society for the Promotion of Science Research Fellow DC2", "日本学術振興会特別研究員 DC2"),
                " ",
                urlPart("https://www.jsps.go.jp/file/storage/general/j-pd/data/saiyo_ichiran/r03/dc2/r3_dc2.pdf#page=22")
            )
        },
        {
            date: "2020/04/01 - 2023/03/23",
            description: seq(
                t(
                    "Kyoto University, Graduate School of Science, Division of Mathematics and Mathematical Sciences, Doctoral Program (Completed)",
                    "京都大学大学院理学研究科 数学・数理解析専攻 博士課程（修了）"
                ),
                " ",
                bracket(link("https://repository.kulib.kyoto-u.ac.jp/dspace/handle/2433/283514", t("Doctoral thesis", "博士論文")))
            ),
            className: "career-divider"
        },
        {
            date: "2018/04/01 - 2020/03/23",
            description: t(
                "Kyoto University, Graduate School of Science, Division of Mathematics and Mathematical Sciences, Master's Program (Completed)",
                "京都大学大学院理学研究科 数学・数理解析専攻 修士課程（修了）"
            )
        },
        {
            date: "2014/04/01 - 2018/03/26",
            description: t(
                "Tokyo Institute of Technology, Department of Mathematics, Bachelor's Program (Graduated)",
                "東京工業大学 理学院数学系 学士課程（卒業）"
            )
        }
    ];

    const careerItems = careerRows.map(({ date, description, ...extra }) => datedItem(date, description, extra));

    const fundingRows = [
        {
            date: "2023/04/25 - 2026/03/31",
            title: t(
                "JSPS KAKENHI Project/Area Number 23KJ0881",
                "日本学術振興会特別研究員奨励費 研究課題・領域番号 23KJ0881"
            ),
            url: t(
                "https://kaken.nii.ac.jp/en/grant/KAKENHI-PROJECT-23KJ0881/",
                "https://kaken.nii.ac.jp/grant/KAKENHI-PROJECT-23KJ0881/"
            )
        },
        {
            date: "2021/04/25 - 2023/03/31",
            title: t(
                "JSPS KAKENHI Project/Area Number 21J11884",
                "日本学術振興会特別研究員奨励費 研究課題・領域番号 21J11884"
            ),
            url: t(
                "https://kaken.nii.ac.jp/en/grant/KAKENHI-PROJECT-21J11884/",
                "https://kaken.nii.ac.jp/grant/KAKENHI-PROJECT-21J11884/"
            )
        }
    ];

    const fundingItems = fundingRows.map(({ date, title, url }) => datedItem(date, seq(title, " ", urlPart(url))));

    const organizeGroupRows = [
        {
            label: "Atelier de Géométrie Arithmétique - 数論幾何学のアトリエ:",
            events: [
                {
                    date: "2025/09/26",
                    title: 'Summer 2025 "Étale homotopy theory and application"',
                    url: "https://ahgt.math.cnrs.fr/activities/ateliers/AGA25-etale_homotopy/",
                    venue: t("RIMS, Kyoto University and Paris", "京都大学数理解析研究所・パリ")
                },
                {
                    date: "2024/07/19",
                    title: 'Summer 2024 "Spaces and perfectoids towards a perfectoid Siegel modular space"',
                    url: "https://ahgt.math.cnrs.fr/activities/ateliers/AGA24-spaces%20perfectoid/",
                    venue: t("RIMS, Kyoto University and Paris", "京都大学数理解析研究所・パリ")
                },
                {
                    date: "2024/02/24",
                    title: 'Winter 2024 "Around the Grothendieck-Teichmüller group"',
                    url: "https://ahgt.math.cnrs.fr/activities/ateliers/AGA24-around%20GT/",
                    venue: t("RIMS, Kyoto University and Paris", "京都大学数理解析研究所・パリ")
                },
                {
                    date: "2023/06/27",
                    title: 'Summer 2023 "Local-global principles and the patching method"',
                    url: "https://ahgt.math.cnrs.fr/activities/ateliers/AGA23-patching/",
                    venue: t("RIMS, Kyoto University and Paris", "京都大学数理解析研究所・パリ")
                }
            ]
        },
        {
            label: "Anabelian Geometry Everywhere:",
            events: [
                {
                    date: "2026/02/19-20",
                    title: t("Anabelian Geometry in Ookayama 2026", "Anabelian Geometry in 大岡山 2026"),
                    url: t(
                        "https://sites.google.com/view/ag-in-ookayama-2026-en/home",
                        "https://sites.google.com/view/ag-in-ookayama-2026-jp/home"
                    ),
                    venue: t("Institute of Science Tokyo", "東京科学大学")
                },
                {
                    date: "2025/09/02-03",
                    title: t("Anabelian Geometry in Yokohama 2025", "Anabelian Geometry in 横浜 2025"),
                    url: t(
                        "https://sites.google.com/view/ag-in-yokohama-2025-en/home",
                        "https://sites.google.com/view/ag-in-yokohama-2025-jp/home"
                    ),
                    venue: t("Kanagawa University", "神奈川大学")
                },
                {
                    date: "2024/03/11-12",
                    title: t("Anabelian Geometry in Tokyo 2024", "Anabelian Geometry in 東京 2024"),
                    url: t(
                        "https://sites.google.com/view/ag-in-tokyo-2024-en/home",
                        "https://sites.google.com/view/ag-in-tokyo-2024-jp/home"
                    ),
                    venue: t("Tokyo Institute of Technology", "東京工業大学")
                }
            ]
        }
    ];

    const organizeLinkRows = [
        {
            name: t("Ookayama Youth Seminar in Algebra", "大岡山代数系若手セミナー"),
            url: "https://sites.google.com/view/ookayama-alge-young-reseachers/home",
            suffix: seq(", ", t("Institute of Science Tokyo", "東京科学大学"))
        }
    ];

    const organizeItems = [
        ...organizeGroupRows.map(({ label, events }) => groupedSection(label, events.map((row) => organizeEvent(row)))),
        ...organizeLinkRows.map((row) => linkRow(row))
    ];

    const membershipRows = [
        {
            name: t("The Mathematical Society of Japan", "一般社団法人 日本数学会"),
            url: t("https://www.mathsoc.jp/en/", "https://www.mathsoc.jp/")
        },
        {
            name: t("Research Fellow, Tokyo Institute of Technology", "東京工業大学特別研究員"),
            url: "https://www.somuka.titech.ac.jp/reiki_int/reiki_honbun/x385RG00002124.html"
        },
        {
            name: "Reviewer for MathSciNet",
            url: "https://www.ams.org/publications/math-reviews/math-reviews"
        },
        {
            name: "“Arithmetic and Homotopic Galois Theory” RIMS-LPP-ENS International Research Network",
            url: "https://ahgt.math.cnrs.fr/members/"
        }
    ];

    const membershipItems = membershipRows.map((row) => linkRow(row));

    const visitRows = [
        {
            date: "2025/11/25-28",
            description: t(
                "Visiting researcher, Department of Mathematical Sciences, Korea Advanced Institute of Science and Technology (KAIST) (Host: Prof. Wansu Kim)",
                "客員研究員, 韓国科学技術院（KAIST）数理科学科（ホスト: Wansu Kim 教授）"
            )
        },
        {
            date: "2024/09/16-29",
            description: t(
                "Participant, France-Japan international scientific exchange “Autumn in Paris 2024”, Paris, France (Host: Dr. Benjamin Collas; AHGT RIMS-CNRS IRN)",
                "参加者, 日仏国際学術交流「Autumn in Paris 2024」（フランス・パリ）（ホスト: Benjamin Collas 博士; AHGT RIMS-CNRS IRN）"
            )
        }
    ];

    const visitItems = visitRows.map(({ date, description }) => datedItem(date, description));

    const homepageRows = [
        { name: t("Shun Ishii", "石井竣"), url: "https://sishii1214.github.io/" },
        { name: "Séverin Philip", url: "https://staff.math.su.se/severin.philip/" },
        { name: t("Ryo Ishizuka", "石塚伶"), url: "https://ryo1203.github.io/" },
        { name: t("Seung-Hyeon Hyeon", "玄承賢"), url: "https://nullstellensatz.org/" },
        { name: t("Lucas Hamada", "浜田 Lucas"), url: "https://sites.google.com/view/lucas-hamada/" },
        { name: t("Takahiro Murotani", "室谷岳寛"), url: "https://researchmap.jp/takahiro_murotani" }
    ];

    const homepageItems = homepageRows.map((row) => linkRow(row));

    window.HOMEPAGE_DATA = {
        pages: {
            en: {
                switchHref: "homepage-jp.html",
                switchLabel: "日本語",
                mobileSwitchLabel: "日本語:",
                header: {
                    quoteHtml: "Ah, but I play dice. It's quite fun.",
                    authorHtml: ""
                }
            },
            ja: {
                switchHref: "homepage-en.html",
                switchLabel: "English Page",
                mobileSwitchLabel: "English Page:",
                header: {
                    quoteHtml: "その言葉こそ、人類の墓標に刻まれるべき一言です。<br>神様、よくわかりませんでした‥‥‥ってね",
                    authorHtml: "- 森博嗣 『四季 冬』 -"
                }
            }
        },
        sections: [
            {
                id: "intro",
                nav: t("Intro", "紹介"),
                title: t("Naganori Yamaguchi", "山口永悟"),
                bodyHtml: introBody
            },
            {
                id: "papers",
                nav: t("Papers", "論文"),
                title: t("Papers", "論文"),
                className: "paper-list",
                items: paperItems
            },
            {
                id: "other_pdfs",
                nav: t("Other PDFs", "その他 PDF"),
                title: t("Other PDFs", "その他 PDF"),
                items: noteItems
            },
            {
                id: "achievements_presentation",
                nav: t("Talks", "講演"),
                title: t("Talks", "講演"),
                ordered: true,
                reversed: true,
                items: talkItems
            },
            {
                id: "background_career",
                nav: t("Career, Education", "職歴、学歴"),
                title: t("Career, Education", "職歴、学歴"),
                items: careerItems
            },
            {
                id: "funding",
                nav: t("Research funds", "研究資金"),
                title: t("Research funds", "研究資金"),
                items: fundingItems
            },
            {
                id: "achievements_organize",
                nav: t("Organize", "主催"),
                title: t("Organize", "主催"),
                items: organizeItems
            },
            {
                id: "membership",
                nav: t("Memberships", "その他所属"),
                title: t("Memberships", "その他所属"),
                items: membershipItems
            },
            {
                id: "visits",
                nav: t("Visits", "研究滞在"),
                title: t("Research Visits", "研究滞在"),
                items: visitItems
            },
            {
                id: "urls",
                nav: t("Nice HPs", "おすすめHP"),
                title: t("Nice Homepages", "おすすめホームページ"),
                items: homepageItems
            }
        ]
    };
})();
