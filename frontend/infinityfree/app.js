/* ================================================================
   COURSE VERIFIER · app.js
   All-in-one frontend: MongoDB Atlas Data API + Client-side logic
   ================================================================ */

'use strict';

// ── Domain Ranges (fixed by course ID) ───────────────────────────
const DOMAIN_RANGES = [
    { label: 'Free', min: 1, max: 22 },
    { label: 'Free to Audit', min: 23, max: 49 },
    { label: 'High Value Low Cost', min: 50, max: 104 },
    { label: 'Foundational', min: 105, max: 659 },
    { label: 'Network Infrastructure', min: 660, max: 1623 },
    { label: 'System & Endpoint', min: 1624, max: 1919 },
    { label: 'Cyber Forensics', min: 1920, max: 2653 },
    { label: 'Data & Application', min: 2654, max: 2979 },
    { label: 'Legal & Ethical', min: 2980, max: 3720 },
];

function getDomainLabel(id) {
    const n = parseInt(id, 10);
    if (isNaN(n)) return 'Uncategorised';
    for (const r of DOMAIN_RANGES) {
        if (n >= r.min && n <= r.max) return r.label;
    }
    return 'Uncategorised';
}

const CATEGORY_RANGES = [
    { label: 'Certificate', min: 1, max: 104 },
    { label: 'Diploma', min: 105, max: 116 },
    { label: 'Bachelors', min: 117, max: 331 },
    { label: 'Masters', min: 332, max: 506 },
    { label: 'Post Graduate Diploma', min: 507, max: 518 },
    { label: 'Certificate', min: 519, max: 637 },
    { label: 'Post Graduate Certificate', min: 638, max: 659 },
    { label: 'Diploma', min: 660, max: 681 },
    { label: 'Bachelors', min: 682, max: 1165 },
    { label: 'Masters', min: 1166, max: 1504 },
    { label: 'Post Graduate Diploma', min: 1505, max: 1526 },
    { label: 'Certificate', min: 1527, max: 1594 },
    { label: 'Post Graduate Certificate', min: 1595, max: 1623 },
    { label: 'Diploma', min: 1624, max: 1626 },
    { label: 'Bachelors', min: 1627, max: 1745 },
    { label: 'Masters', min: 1746, max: 1876 },
    { label: 'Post Graduate Diploma', min: 1877, max: 1885 },
    { label: 'Certificate', min: 1886, max: 1909 },
    { label: 'Post Graduate Certificate', min: 1910, max: 1919 },
    { label: 'Diploma', min: 1920, max: 1930 },
    { label: 'Bachelors', min: 1931, max: 2317 },
    { label: 'Masters', min: 2318, max: 2591 },
    { label: 'Post Graduate Diploma', min: 2592, max: 2613 },
    { label: 'Certificate', min: 2614, max: 2637 },
    { label: 'Post Graduate Certificate', min: 2638, max: 2653 },
    { label: 'Diploma', min: 2654, max: 2661 },
    { label: 'Bachelors', min: 2662, max: 2796 },
    { label: 'Masters', min: 2797, max: 2937 },
    { label: 'Post Graduate Diploma', min: 2938, max: 2941 },
    { label: 'Certificate', min: 2942, max: 2968 },
    { label: 'Post Graduate Certificate', min: 2969, max: 2979 },
    { label: 'Diploma', min: 2980, max: 3000 },
    { label: 'Bachelors', min: 3001, max: 3420 },
    { label: 'Masters', min: 3421, max: 3631 },
    { label: 'Post Graduate Diploma', min: 3632, max: 3661 },
    { label: 'Certificate', min: 3662, max: 3702 },
    { label: 'Post Graduate Certificate', min: 3703, max: 3720 }
];

function getCategoryLabel(id) {
    const n = parseInt(id, 10);
    if (isNaN(n)) return 'Uncategorised';
    for (const r of CATEGORY_RANGES) {
        if (n >= r.min && n <= r.max) return r.label;
    }
    return 'Uncategorised';
}


// ── Motivational lines ───────────────────────────────────────────────────────
const MOTIVATIONAL_LINES = [
    "Every solved course brings Panvel closer.",
    "Small fixes today, clean catalog tomorrow.",
    "One course at a time. You've got this.",
    "Verify today, celebrate in Panvel.",
    "Consistency beats intensity — keep solving.",
    "Kal nikalna hai, aaj solve karo.",
    "Each click makes the data cleaner.",
    "Progress, not perfection.",
    "Clear the queue, own the day.",
    "One verified course is one problem less.",
];

const TOAST_MOTIVATIONS = [
    "Onward to Panvel!",
    "Keep the streak alive.",
    "Verified like a pro.",
    "Another one bites the dust.",
    "Small win, big catalog.",
    "Data gets cleaner with every click.",
];

let motivationIndex = 0;
let motivationTimer = null;

function rotateMotivation() {
    const el = document.getElementById('motivation');
    if (!el) return;
    el.classList.add('fade');
    setTimeout(() => {
        motivationIndex = (motivationIndex + 1) % MOTIVATIONAL_LINES.length;
        el.textContent = MOTIVATIONAL_LINES[motivationIndex];
        el.classList.remove('fade');
    }, 400);
}

function startMotivationRotation() {
    const el = document.getElementById('motivation');
    if (!el) return;
    el.textContent = MOTIVATIONAL_LINES[0];
    if (motivationTimer) clearInterval(motivationTimer);
    motivationTimer = setInterval(rotateMotivation, 8000);
}

function randomToastMotivation() {
    return TOAST_MOTIVATIONS[Math.floor(Math.random() * TOAST_MOTIVATIONS.length)];
}

// ── Fees Link Lookup ──────────────────────────────────────────────────────────
// Maps "institute_name|||course_name" (ASCII-normalised, lowercased) → fee page URL
// Generated from backend/fees.xlsx  (804 entries)
const FEES_MAP = {"acharya nagarjuna university|||diploma in cyber threats and security":"https://moocs.anuonline.ac.in/diploma-in-cyber-threats-security.html","adamas university|||b.tech computer science and  engineering (cyber security and forensics)":"https://adamasuniversity.ac.in/wp-content/uploads/2024/12/Approved-Programs-Fees-for-AY-2025-26-Website-3_removed.pdf","alliance univeristy|||b. tech. in computer science & engineering  cyber security":"https://www.alliance.edu.in/uploads/fee-structure/btech-cse-cyber-security-fee2026.pdf","amity university jaipur|||m.sc. (cyber security)":"https://www.amity.edu/course-details.aspx?fd=nagExDxhy1Q=&cfn=PXPP3/bjA/oQVaONesCQdQ==","amrita vishwa vidyapeetham|||b. tech. in computer science and engineering (cyber security)":"https://webfiles.amrita.edu/2025/01/btech-fee-structure-2025-26.pdf","amrita vishwa vidyapeetham|||b.c.a. (honours) in cyber security":"https://www.amrita.edu/program/b-c-a-honours-in-cyber-security/#fee-structure-sec","amrita vishwa vidyapeetham|||m.c.a. in cyber security":"https://www.amrita.edu/program/mca-cyber-security/#feestructure","anjaneya university|||b.tech. - computer science and engineering in cyber security":"https://anjaneyauniversity.ac.in/admission-fee-structure","anurag university|||b.tech in cse cyber security":"https://nba.anurag.edu.in/tuition-fee/","arka jain university|||bca (cyber security)":"https://arkajainuniversity.ac.in/admissions/course-fee-2/","aryavart international university|||bca - information security and cyber forensics":"https://aiuniversity.edu.in/course_details.php?id=11","aryavart international university|||mca - cloud technology & information security":"https://aiuniversity.edu.in/course_details.php?id=19","asian school of cyber law|||diploma in cyber law":"https://www.asianlaws.org/diploma-in-cyber-law.php","atal bihari vajpayee indian institute of information technology and management|||m. tech. (information and cyber security)":"https://www.iiitm.ac.in/images/2023/June_2023/Fee_Structure_July_2023.pdf","avantika university|||bachelor of technology (btech) in cyber security":"https://www.avantikauniversity.edu.in/downloads/Fees_2025-26.pdf","babu banarasi das university|||bca in cyber security and forensics":"https://bbdu.ac.in/school-of-computer-applications/soca-programs/bca-in-cyber-security-and-forensics","bahra university|||b.tech in computer science & engineering (cyber security)":"https://bushimla.in/programs/b-tech-cse-cyber-security/","bharatiar university|||certificate course in cyber security":"https://b-u.ac.in/23/department-computer-applications-fees-structure","bharatiar university|||msc cybersecurity":"https://b-u.ac.in/23/department-computer-applications-fees-structure","bhartiya vidyapeeth|||diploma in cyber law":"https://bharatividyapeethdistancemba.com/cyberLaw-distance.html","birla institute of technology & science|||post graduate diploma in automotive cybersecurity":"https://bits-pilani-wilp.ac.in/pgd/post-graduate-diploma-in-automotive-cybersecurity.php","brainware university|||btech cyber security":"https://www.brainwareuniversity.ac.in/degree-programmes/btech-cyber-security.php","brainware university|||msc adv.networking cyber securtiy":"https://www.brainwareuniversity.ac.in/pg-degree-programmes/msc-advanced-networking-cyber-security","cdac (centre for development of advanced computing)|||pg diploma in cyber security & forensics (pg-dcsf)":"https://www.cdac.in/index.aspx?id=DAC&courseid=49","central university of jammu|||pg diploma in cyber forensics":"https://www.cujammu.ac.in/static/homepage/admissions/BTech_CSE/2025/PGD/FS.pdf","centurion university|||master of science in cyber security & digital forensics":"https://cutm.ac.in/course-fees/","chaitanya bharathi institute of technology (osmania university)|||b.e in cse (internet of things and cyber security including block chain technology)":"https://www.cbit.ac.in//wp-content/uploads/2019/01/Tution-Fee.pdf","chandigarh university|||bachelor of engineering (hons.) (computer science and engineering) (cyber security) (in association with ibm)":"https://www.cuchd.in/ibm/be-cse-cyber-security.php","chitkara university|||mba program with major in cyber security":"https://onlinechitkarau.com/online-mba-in-cyber-security/","coep technological university|||mtech cyber security":"https://www.coeptech.ac.in/wp-content/uploads/2025/07/Mtech-Admitted-2024-25-Auto-Tech-Data-Sci-Cyb-Sec.pdf","coep technological university|||mtech information security":"https://www.coeptech.ac.in/wp-content/uploads/2024/07/M.Tech_M.Planning-First-Year-M.Tech-All-Programs-_-Planning-_.pdf","coer university, roorkee|||b.tech cse with specialization in cyber security":"https://coeruniversity.ac.in/admissions/course-eligibility-fee-structure","datta meghe institute of higher education and research|||mca networking and cyber security":"https://www.dmiher.edu.in/uploads/topics/admission-24/Fee%20structure%20SAS%20Regular%20Programs.pdf","dayananda sagar university|||b.tech - computer science & engineering (cyber security)":"https://dsu.edu.in/abt-bcom/106-admission/2002-dsu-fee-structure?gad_source=1&gad_campaignid=21292412549&gbraid=0AAAAAqmcaYAU2u1_GG3C76VZFjy40u6lG&gclid=CjwKCAjw49vEBhAVEiwADnMbbOferwxwRpi4K-8zoQ2x_20mXMB2OYCnIivwSN5iff4ug9ld4BFQaRoC7rgQAvD_BwE","dbs global university|||b.tech in computer science and engineering (cse) with specialization in cyber security":"https://drive.google.com/file/d/1UWppPRUF0hIAdYamyg1OAgmUp3w11eSN/view?usp=sharing","dev bhoomi uttarakhand university|||bca in cyber security":"https://www.dbuu.ac.in/engineering/bca-cyber-security.php","dit universty|||b.tech in computer science & engineering with specialization in cybersecurity and privacy":"https://www.dituniversity.edu.in/assets/frontend/course-structure/btech-cse-fee-structure-2025.pdf","dj sanghvi (mumbai university)|||b.tech computer science and engineering (iot and cyber security with block chain technology)":"https://www.djsce.ac.in/docs/Fees%20Structure%20First%20Year%20B.%20Tech%2025-26.pdf","dr. babasaheb ambedkar open university, ahmedabad|||master of science cyber security (msccs)":"https://ciqa.baou.edu.in/upload/doc/eba736c3e1c2028d18abe79e55a76ae8.pdf","ellenki college of engineering and technology (jawaharlal nehru technological university hyderabad)|||b.tech cse (cybersecurity)":"https://ellenkicet.ac.in/fee-structure/","g. h. raisoni college of engineering nagpur (rashtrasant tukadoji maharaj nagpur university)|||bsc (cyber security)":"https://ghrcemn.raisoni.net/fees-structure","galgotias university|||b.sc (hons ) computer science (cyber security)":"https://www.galgotiasuniversity.edu.in/public/uploads/media/d8G8oflKUhZdnUkN0LjGGxqFmzjKcBgBIpwQL7Ph.pdf","ganga institute of technology and management (maharshi dayanand university  rohtak)|||mtech cyber forensics and information security":"https://mdu.ac.in/UpFiles/UpPdfFiles/2021/Jan/2_01-22-2021_16-17-29_headwise%20fee%20structure%20of%20affiliated%20colleges.pdf","garden city university|||bsc data science and cybersecurity":"https://www.gardencity.university/admissions/fee-structure/domestic-nri-fee-structure/","gayatri vidya parishad college of engineering, visakhapatnam (andhra university)|||m.tech. (cyber security)":"https://gvpce.ac.in/feestruc.php","girjandha chowdhary university|||m.sc. in cyber security":"https://gcuniversity.ac.in/wp-content/uploads/2024/02/GCU-Fees-structure-for-the-session-2024-25.pdf","government institute of forensic science (dr. babasaheb ambhedkar marathwada university)|||b.sc forensic science":"https://gifsa.ac.in/b-sc-forensic/","graphic era university|||b.tech cse (hons.) in cybersecurity":"https://geu.ac.in/fee/btech-cse-cybersecurity","gujarat university|||master of science in cyber security and forensics":"https://drive.google.com/file/d/1xFWvTLb89FWQgiB6--6m46k65eBbRV4h/view?usp=sharing","gujarat university|||m.sc. it in network security":"https://drive.google.com/file/d/1xFWvTLb89FWQgiB6--6m46k65eBbRV4h/view?usp=sharing","guru ghasidas vishwavidyalaya|||m.sc forensic science":"https://www.ggu.ac.in/media/attachments/department/admissionNews/Final_Semesterwise_fee_2025-26_05.03.25.pdf","guru ghasidas vishwavidyalaya|||bsc forensic science":"https://www.ggu.ac.in/media/attachments/department/admissionNews/Final_Semesterwise_fee_2025-26_05.03.25.pdf","haldia institute of technology (maulana abul kalam azad university of technology)|||b.tech in computer sc. & engg (cyber security)":"https://hithaldia.ac.in/fee-structure","haridwar university|||b.sc (computer science) cyber security":"https://huroorkee.ac.in/academics/programs/courses/btech-hons-iot-cyber-security-including-blockchain-technology-data-science","haridwar university|||b.tech. hons. cyber security including blockchain technology":"https://www.iujaipur.edu.in/programs/ugprograms/bsc-forensic-science","indian institute of information technology kottayam|||b.tech in computer science and engineering with specialisation in cyber security":"https://www.iiitkottayam.ac.in/#!/admission","indian institute of information technology kottayam|||mtech cyber security for working professionals":"https://www.iiitkottayam.ac.in/#!/mtech_cyber","indian institute of information technology kottayam|||mtech cyber security and digital forensics":"https://emtech.iiitkottayam.ac.in/","indian institute of information technology sri|||mtech in cybersecurity":"https://iiits.ac.in/academics/m-tech-programme/fee-structure/","indian institute of management indore|||executive programme in artificial intelligence and cyber security for organizations":"https://iith.ac.in/academics/assets/files/fee/2025/IITH-Fee-Structure-for-Jul-Dec-2025-Semester_Newly-Enrolled-Students.pdf","indian institute of technology bhilai|||executive mtech in cybersecurity and ethical hacking":"https://iitbhilai.digivarsity.com/executive-mtech-in-cyber-security-and-ethical-hacking.html","indian institute of technology guwahati|||advanced certification in cyber security":"https://iitg.ac.in/acad/admission/imp_info/fee.php","indian institute of technology guwahati|||advanced professional certification programme in cybersecurity and ethical hacking":"https://www.jaroeducation.com/advanced-professional-certification-programme-in-cybersecurity-and-ethical-hacking-eict-iit-guwahati","indian institute of technology hyderabad|||certification program in ai and cybersecurity":"https://aicybercourse.ai.iith.ac.in/assets/CyberAI-brochure.pdf","indian institute of technology indore|||master of science in cyber security and cyber law":"https://cscl.iiti.ac.in/","indian institute of technology jammu|||pg diploma in cybersecurity":"https://www.iitjammu.ac.in/news/2023/IIT%20Jammu%20TimesPro%20offers%20Post%20Graduate%20Diploma%20in%20Cyber%20Security_Brochure.pdf","indian institute of technology kanpur|||advanced certification program in cyber security and cyber defense":"https://talentsprint.com/course/cyber-security-iit-kanpur","indian institute of technology kanpur|||introduction to cybercrime":"https://www.eicta.iitk.ac.in/payment/introduction-to-cybercrime?mode=SELF_PACED","indian institute of technology madras|||professional certificate programme in cybersecurity and ai":"https://digitalskills.iitmpravartak.org.in/course_details.php?courseID=385&cart=","indian institute of technology palakkad|||post graduation certification in cyber security":"https://www.jaroeducation.com/cyber-security-iit-palakkad","indian institute of technology patna|||bachelor of science (bs) in artificial intelligence & cyber security":"https://drive.google.com/file/d/1-QBDs5b7vTTtNCNciINo9Wjz0zo8Hp-7/view","indian institute of technology roorkee|||certificate in cybersecurity and ethical hacking with applied ai":"https://tih.iitr.ac.in/training-courseDetails/80","indian institute of technology roorkee|||executive post graduate certification in cyber security and ethical hacking":"https://tih.iitr.ac.in/training-courseDetails/31","indian institute of technology roorkee|||pg certificate program in ai/genai powered cybersecurity":"https://futurense.com/iit-roorkee/ai-genai-cybersecurity-pg","indian institute of technology ropar|||cyber security essentials":"https://www.tcsion.com/hub/iit-ropar-certificate-program/cyber-security/","indian academy of cyber law and management|||certification in cyber law":"https://www.ialm.academy/courses","indian law institute|||pg diploma in cyber law":"https://ili.ac.in/details.php?catid=24","indian school of business (isb)|||cybersecurity for leaders":"https://online-em.isb.edu/cybersecurity-for-leaders","indira college of commerce and science (savitribai phule pune university)|||b.sc cyber security":"https://drive.google.com/file/d/1wE0JO5WJDBNlmo_xq4z5XjWxBtIYAQgL/view?usp=sharing","indus university|||bsc cyber security":"https://indusuni.ac.in/ug-admissions/","aditya university|||msc cyber security & digital forensics":"https://www.adityauniversity.in/admissions/programs-eligibility-fee-structure","aditya university|||bsc cyber security & digital forensics":"https://www.adityauniversity.in/admissions/programs-eligibility-fee-structure","international forensics science institute|||certification (expert / gold) in cyber law":"https://www.ifsedu.in/fee-structure/","international forensics science institute|||pg certification in cyber law":"https://www.ifsedu.in/fee-structure/","international forensics science institute|||professional specialized certification in cyber law":"https://www.ifsedu.in/fee-structure/","international forensics science institute|||universal certification in cyber law":"https://www.ifsedu.in/fee-structure/","invertis university|||b.tech in cse (cloud computing and cyber security)":"https://www.invertisuniversity.ac.in/ug-programmes/btech-in-cse-with-specialization-in-cloud-computing","j.j. college of engineering (anna university)|||b.e. computer science and engineering (cyber security)":"https://drive.google.com/file/d/1vog0rWXRzF2SF33kPUkXoESePa2Hb8wr/view?usp=sharing","jai bharath arts and science college (mahatma gandhi university)|||b.sc. cyber forensic":"https://campusways.com/wp-content/uploads/2023/02/Jai-Bharath-Fee-2023-24.pdf","jain university|||bca in cyber security":"https://jain.onlinedegreecourse.in/bca-in-cyber-security/","jain university|||mca in cyber security":"https://onlinejain.in/mca-cyber-security/","jaypee institute of information technology|||b. tech cse (cyber-security)":"https://www.jiit.ac.in/prospective-student/admission/fee-structure","jecrc university|||b.tech. (cse) cyber security (ec-council, usa)":"https://jecrcuniversity.edu.in/admission/b-tech-cse-cyber-security-ec-council-usa/","jecrc university|||bca cyber security (ec-council, usa)":"https://jecrcuniversity.edu.in/admission/bca-cyber-security-ec-council-usa/","jecrc university|||mca cyber security (ec-council, usa)":"https://jecrcuniversity.edu.in/admission/mca-cyber-security-ec-council-usa-2-years/","jk lakshmipat university - [jklu], jaipur|||b.tech cse (cybersecurity)":"https://jklu.edu.in/admissions/fee-structure","amrita vishwa vidyapeetham amritapuri|||m. tech. in cyber security systems & networks":"https://webfiles.amrita.edu/2022/05/M.Tech-fee-structure.pdf","karunya institute of technology and sciences|||m.tech cyber security":"https://admissions.karunya.edu/sites/admissions/files/uploads/downloads/2024/Fees/INR/M.Tech.%20Fee%20Structure%202024-25%20-%20Indian.pdf","kalinga institute of industrial technology|||b.tech computer science and engineering with specialization cyber security":"https://drive.google.com/file/d/121extnlXkoHQN1PRdacr7yKqTiQ3P52n/view?usp=sharing","kalinga institute of industrial technology|||b.tech computer science and engineering with specialization internet of things and cyber security including block chain technology":"https://drive.google.com/file/d/1AC6Yiz3u7QiB25eIvGYLP9EG_jfGv2MJ/view?usp=sharing","kl university|||m.tech  digital forensics and cyber security":"https://www.kluniversity.in/pgfee.aspx","kle society's law college (kle technological university)|||pg diploma in cyber and information technology law":"https://www.klelawcollege.org/admission-process/","kr mangalam university|||b.sc. (hons.) cyber security":"https://www.krmangalam.edu.in/fee-structure","kr mangalam university|||b.tech. cse (cybersecurity) with academic support of ec-council & ibm":"https://www.krmangalam.edu.in/fee-structure","kr mangalam university|||bca (cyber security) with academic support of ec council":"https://www.krmangalam.edu.in/fee-structure","kristu jayanti university|||bca cyber security":"https://drive.google.com/file/d/1QwtnexpF48byeva1pVwdzKUBS3U3vxc2/view?usp=sharing","lovely professional university|||b.tech. hons. (cse) - cyber security and blockchain":"https://www.lpu.in/programmes/engineering/b-tech-hons-cse-cyber-security-and-blockchain","loyola institute of technology (anna university)|||b.e. computer science and engineering (cyber security)":"https://drive.google.com/file/d/1vog0rWXRzF2SF33kPUkXoESePa2Hb8wr/view?usp=sharing","malla reddy vishwavidyaapeeth|||b.tech in computer science & engineering (cyber security)":"https://mrem.ac.in/admissions/fee-structure/","manav rachna international institute of research and studies|||b.tech cse (hons.) - digital forensics and cyber security":"https://manavrachna.edu.in/mriirs/academics/btech-cse-digital-forensics-and-cyber-security#feeDetails","manav rachna international institute of research and studies|||bca with specializations in cyber security in asssociation with knowledge partner":"https://manavrachna.edu.in/mriirs/academics/bca-cyber-security#feeDetails","mangalayatan university aligarh|||btech cse in cyber security":"https://www.mangalayatan.in/courses-fee-structure/","mangalayatan university aligarh|||ll.m. in cyber law":"https://www.mangalayatan.ac.in/fee-schedule/","manipal academy of higher education|||b. tech cse (cybersecurity)":"https://drive.google.com/file/d/15Y7NczhV3ho_3JaKdFEMywLxbsedIDxq/view?usp=sharing","manonmaniam sundaranar university|||m.sc.cyber security":"https://www.msuniv.ac.in/it_programmed_courses.php","marwadi university|||cyber security (mtech)":"https://www.marwadiuniversity.ac.in/wp-content/uploads/2026/05/Program_Fees_2026-27.pdf","mgm university|||b. tech. computer science and engineering (cyber security)":"https://mgmu.ac.in/admissions/program/b-tech-computer-science-and-engineering-cyber-security?srsltid=AfmBOopxQ5BR5OGsbpO2VFJ_EmZKRp7m77YvlOWRGbfrdlgXRPaEP84J","mgm university|||b. tech. computer science and engineering (iot, cyber security including blockchain technology)":"https://mgmu.ac.in/assets/docs/Final%20Fee%20Structure%20for%20AY%202023-24%20(With%20Univ%20Common%20Fee).pdf?srsltid=AfmBOootRXNUXcZznscDeWVpSvQ9a3Nx5tdS76gAkj3GkPwfvmYsWD4B","model institute of engineering & technology, jammu  (university of jammu)|||b.tech cse (cybersecurity)":"https://mietjmu.in/admission_miet/tuition-fees/","mizoram university|||executive diploma in cyber security":"https://www.mzuonline.in/executive_diploma_cyber-security.html","mohan babu university|||b. tech. cse (cyber security)":"https://www.mbu.asia/wp-content/uploads/2025/07/MBU-Fee-Structrure-2025-26New.pdf","muthayammal engineering college (anna university)|||b. e. computer science and engineering (cyber security)":"https://drive.google.com/file/d/1vog0rWXRzF2SF33kPUkXoESePa2Hb8wr/view?usp=sharing","nalsar university|||pg diploma in cyber law":"https://apply.nalsar.ac.in/ddeapplicationform","nandha engineering college (anna university)|||b.e. computer science and engineering (cyber security)":"https://drive.google.com/file/d/1vog0rWXRzF2SF33kPUkXoESePa2Hb8wr/view?usp=sharing","national forensic sciences university|||certificate course on network forensics":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national forensic sciences university gandhinagar|||m.sc. cyber security":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national forensic sciences university gandhinagar|||m.tech. artificial intelligence and data science (specialization in cyber security)":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national forensic sciences university gandhinagar|||m.tech. cyber security":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","nelson business school|||mba in cyber security":"https://nbs.org.in/mba-in-cyber-security/","neotia university|||b.tech computer science & engineering with specialization in cyber security":"https://www.tnu.in/admissions/fee-structure/indian-students-2/","niilm university|||bca (cyber security)":"https://www.niilmuniversity.ac.in/page/domestic-fee","national institute of technology agartala|||m.tech in cyber security":"https://www.nita.ac.in/Prospectus.pdf","national institute of technology calicut|||mtech cse (information security)":"https://nitc.ac.in/imgserver/uploads/attachments/nit-calicut-fee-structure-for-pg-and-phd-for-the-ay-2026-27--b-stylecolorrednewb_2336_0.pdf","malaviya national institute of technology, jaipur|||pg certification in cyber security and ethical hacking":"https://intellipaat.com/pg-certification-cyber-security-ethical-hacking-mnit/","national institute of technology jamshedpur|||m.tech information systems and security":"https://nitjsr.ac.in/backend/uploads/dean_notices/add/a81c83b4-9db5-4f33-bb34-c495f58399c6-NOTICE-S-47-2024%20The%20Fee%20structure%20for%20Academic%20Session%202024-25%20for%20all%20UG,%20PG%20and%20PhD%20(2024%20Batch%20onwards).pdf","national institute of technology, kurukshetra|||m.tech cyber security":"https://nitkkr.ac.in/wp-content/uploads/2023/06/Fee-Structure-for-M.Tech_.-2023-25-GeneralOBC-EWS.pdf","national institute of technology patna|||m.tech in cyber security":"https://drive.google.com/file/d/1qSQMYVRWFoWXad4Z765LtsPMXBofYKzK/view","national institute of technology surathkal|||mtech cse (information security)":"https://www.nitk.ac.in/document/attachments/8447/FEE_STRUCTURE_2025-26_.pdf","national institute of technology warangal|||m.tech computer science and information security":"https://nitw.ac.in/api/static/files/PG_fee_structure_2023-6-25-17-47-31.pdf","national law institute university bhopal|||master of cyber law and information security":"https://drive.google.com/file/d/1Z1KFNdzia7ipVYnFC7SfC1rbHmLO0Ryt/view?usp=drive_link","narsee monjee institute of management studies|||b.tech computer science & engineering (cyber security)":"https://drive.google.com/file/d/1PrOXmM-8uZHmQDc1JC7dy8RYRUkTzuBY/view?usp=sharing","noida institute of engineering and technology (dr. a.p.j. abdul kalam technical university)|||b. tech cse (cyber-security)":"https://www.niet.co.in/pdf/fees-details/2024/B.Tech%20M.Tech%20fee%20structure%202024.pdf","om sterling global university|||b.tech. cse / cse leet (cyber security)":"https://www.osgu.ac.in/wp-content/uploads/2024/05/National-Brouchure-2024-25-2.pdf","om sterling global university|||bca (cyber security)":"https://www.osgu.ac.in/wp-content/uploads/2024/05/National-Brouchure-2024-25-2.pdf","pandit deendayal energy university|||m.tech. in cyber security":"https://api.pdeu.ac.in/pdpu/resources/mtech-poilcy.pdf","panipat institute of engineering & technology (kurukshetra university)|||b.tech cse (cybersecurity)":"https://www.piet.co.in/wp-content/uploads/2025/04/Fee-Structure-25-26-01.04.25.pdf","pimpri chinchawad university|||bsc (computer science cybersecurity)":"https://pcu.edu.in/fees-structure.php","pp savani university|||b.tech. computer science engineering (cyber security)":"https://www.ppsu.ac.in/pp-savani-university-fees-structure-2026-2027","rashtriya raksha university|||b.tech. in cs&e with specialization in cyber security":"https://legacy.rru.ac.in/wp-content/uploads/2024/05/Fees-Structure-SITAICS-14May2024.pdf","rashtriya raksha university|||m.sc. in cyber security and digital forensics":"https://legacy.rru.ac.in/wp-content/uploads/2024/05/Fees-Structure-SITAICS-14May2024.pdf","rashtriya raksha university|||m.tech. in cyber security":"https://legacy.rru.ac.in/wp-content/uploads/2024/05/Fees-Structure-SITAICS-14May2024.pdf","rashtriya raksha university|||post graduate diploma in cyber security & digital forensics(pgdcsdf)":"https://legacy.rru.ac.in/wp-content/uploads/2024/05/Fees-Structure-SITAICS-14May2024.pdf","reva university|||b.tech in computer science and engineering (internet of things and cyber security including block chain technology)":"https://drive.google.com/file/d/1fmepJ31Dfjm_qh5g_wunPXVkMUXKCSpc/view?usp=drive_link","rv university|||b.sc. (hons.) -criminology, cyber law & forensic science":"https://rvu.edu.in/fee-structure/fee-structure-ay-2026-27/","sage university bhopal|||b. tech. cyber security & forensic":"https://sageuniversity.edu.in/assets/pdf/Fee-Structure.pdf","sage university indore|||m. tech. cyber security":"https://sageuniversity.in//assets/feestructure/fees_structure.pdf","sandip university nashik|||b.tech cse - specialisation in cyber security and forensics":"https://www.sandipuniversity.edu.in/fees-structure.php","sanskaram university|||b.sc. (hons.) cyber security":"https://drive.google.com/file/d/16T7N0gxtNVuxgxhni4RJi-zzdABItPFe/view?usp=drive_link","sanskaram university|||m.sc. in cyber security":"https://drive.google.com/file/d/1YZ3qHSsMEWQZISevdbOeWxvGePUOcQKA/view?usp=sharing","sanskriti university|||b.tech cloud technology and cyber security":"https://www.sanskriti.edu.in/admissions/eligibilty-and-fee-structure.php","sanskriti university|||bca cyber security":"https://www.sanskriti.edu.in/admissions/eligibilty-and-fee-structure.php","sanskriti university|||b. tech cse with information security and cyber forensics":"https://www.sanskriti.edu.in/admissions/eligibilty-and-fee-structure.php","savitribhai phule pune university|||post graduate diploma in cyber security and india's national security":"http://sppudocs.unipune.ac.in/sites/news_events/Lists/News%20and%20Announcements/Attachments/8584/5%20Admission%20Notice%20Advanced%20Course%20in%20Cyber%20Security%20and%20India%E2%80%99s%20National%20Security%202024.pdf","sgt university|||bachelor of science (hons. with research) forensic science":"https://sgtuniversity.ac.in/science/programmes/bsc-in-forensic-science","sgt university|||m.sc. digital forensics and information security":"https://sgtuniversity.ac.in/science/programmes/msc-digital-forensics","shah & anchor kutchhi engg. college|||b.tech. cyber security":"https://www.sakec.ac.in/wp-content/uploads/2024/08/FE_DSE_ME_Working_Prof_FEES_STRUCTURE_2024_25-1.pdf","shaheed sukhdev college of buisness studies ( university of delhi)|||post graduate diploma in cyber security and law":"https://sscbs.du.ac.in/wp-content/uploads/2025/09/fee-structure-PGDCSL-1.pdf","shiv nadar university|||b.tech computer science & engineering cyber security":"https://drive.google.com/file/d/1WP7wOJPKCE_JS6T5v8O1DCnaFN1I_AHo/view?usp=sharing","shoolini university|||b tech cse cyber security":"https://shooliniuniversity.com/shoolini-university-fee-structure","shri ramswaroop memorial university|||b.tech. in cse (cyber security) with l&t":"https://srmu.ac.in/program/b-tech-cse-cyber-security","shri rawatpura sarkar university|||m.tech.in cyber forensics engineering":"https://sruraipur.ac.in/sru/fees-structure","shri vishnu engineering college for women (jawaharlal nehru technological university kakinada )|||b.tech cse (cybersecurity)":"https://svecw.edu.in/programmes-fee-structure/","sikkim manipal university (smit)|||b.tech cse (iot & cyber security including blockchain technology)":"https://www.smu.edu.in/smit/fee-structure.php","siksha o anusadhan|||b.tech computer science and engineering (cyber security)":"https://drive.google.com/file/d/14vQGSnsi6qpUzaxu8ssrbwYbrsY4IZzz/view?usp=sharing","silver oak university|||m.sc. cyber security & digital forensics (2 years)":"https://silveroakuni.ac.in/branches/msc-cs","sr university|||b.tech - computer science & engineering (cyber security)":"https://sru.edu.in/fee-scholarship","sri krishna college of engineering and technology (anna universtiy)|||b.e. computer science and engineering (cyber security)":"https://drive.google.com/file/d/1vog0rWXRzF2SF33kPUkXoESePa2Hb8wr/view?usp=sharing","sri ramachandra institute of higher education and research|||b.tech.  computer science and engineering(cybersecurity and internet of things)":"https://sriramachandra.edu/programme/b-tech-computer-science-and-engineeringcybersecurity-and-internet-of-things/","sri sri university|||b.tech. cse cyber security & cyber defense (cscd)":"https://srisriuniversity.edu.in/wp-content/uploads/2025/03/B.Tech-DS-25.pdf","srm university sikkim|||b.tech in cse - cyber security":"https://srmus.ac.in/program-fee-structure","st joseph's university bengaluru|||pg diploma in cyber security":"https://drive.google.com/file/d/1-FrmHQr20RZpK-hKQpuAqE6sP5E-xWLX/view?usp=sharing","st. joseph's college of engineering (anna university)|||b.e. computer science and engineering (cyber security)":"https://drive.google.com/file/d/1vog0rWXRzF2SF33kPUkXoESePa2Hb8wr/view?usp=sharing","national forensic sciences university gandhinagar|||m.sc. digital forensics and information security":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","galgotias university|||b.tech in computer science and engineering (cyber security)":"https://www.galgotiasuniversity.edu.in/public/uploads/media/d8G8oflKUhZdnUkN0LjGGxqFmzjKcBgBIpwQL7Ph.pdf","national forensic sciences university gandhinagar|||ll. m. (cyber law and cyber crime investigation)":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national institute of electronics & information technology kohima|||m.tech cyber forensics and information security":"https://nielit.ac.in/fee-structure.php","national institute of electronics & information technology ropar|||m.tech cyber forensics and information security":"https://nielit.ac.in/fee-structure.php","nielit deemed to be university- srinagar|||m.tech cyber forensics":"https://nielit.ac.in/fee-structure.php","national forensic sciences university goa|||m.sc. cyber security":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national forensic sciences university bhopal|||m.sc. cyber security":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national forensic sciences university chennai|||m.sc. cyber security":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national forensic sciences university nagpur|||m.sc. cyber security":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national forensic sciences university goa|||m.tech. artificial intelligence and data science (specialization in cyber security)":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national forensic sciences university delhi|||m.sc. digital forensics and information security":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national forensic sciences university raipur|||m.sc. digital forensics and information security":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national forensic sciences university jaipur|||m.sc. digital forensics and information security":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national forensic sciences university bhubneshwar|||m.sc. digital forensics and information security":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national forensic sciences university goa|||m.sc. digital forensics and information security":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national forensic sciences university bhopal|||m.sc. digital forensics and information security":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national forensic sciences university bhubneshwar|||ll. m. (cyber law and cyber crime investigation)":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","niilm university|||b.sc. (cyber security)":"https://www.niilmuniversity.ac.in/page/domestic-fee","niilm university|||m.sc. (cyber security)":"https://www.niilmuniversity.ac.in/page/domestic-fee","niilm university|||diploma leet - cyber security":"https://www.niilmuniversity.ac.in/page/domestic-fee","niilm university|||b.voc. (cyber security)":"https://www.niilmuniversity.ac.in/page/domestic-fee","niilm university|||b.tech (cse) cyber security":"https://www.niilmuniversity.ac.in/page/domestic-fee","niilm university|||bba (cyber security)":"https://www.niilmuniversity.ac.in/page/domestic-fee","niilm university|||m.tech cse (cyber security)":"https://www.niilmuniversity.ac.in/page/domestic-fee","sir padmapat singhania university|||btech cse with specialization - cyber security (collaboration with l&t edutech)":"https://www.spsu.ac.in/apply-now/fee-structure/","sri sri university|||bca (cyber security)":"https://srisriuniversity.edu.in/wp-content/uploads/2025/03/BCA-25.pdf","sri sri university|||m.tech. in cyber security & digital forensic":"https://srisriuniversity.edu.in/m-tech-in-cyber-security-digital-forensic/","srinath university|||bca in cyber securtiy":"https://srinathuniversity.ac.in/bca-in-cyber-security-in-association-with-cyber-dojo/","srinath university|||m.tech cyber security":"https://srinathuniversity.ac.in/master-of-technology-cybersecurity/","srm university sonepat|||b.tech. cse (cyber security)":"https://srmuniversity.ac.in/admission-fee-structure","st joseph's university bengaluru|||master of science (m.sc.) in cyber security and artifical intelligence":"https://drive.google.com/file/d/1-FrmHQr20RZpK-hKQpuAqE6sP5E-xWLX/view?usp=sharing","suresh gyan vihar university jaipur|||b.tech computer science & engineering with cyber security":"https://www.gyanvihar.org/wp-content/uploads/attach/fees-structure.pdf","swami rama himalayan university|||b.tech. (hons.) cse with specializations in artificial intelligence & machine learning, data science & machine learning and cyber security.":"https://srhu.edu.in/wp-content/uploads/2025/03/Fee-Structure-2025.pdf","swami vivekananda university|||b.sc(h) in advanced networking and cyber security":"https://www.swamivivekanandauniversity.ac.in/resource/assets/pdf/2026%20Fees%20Structure%2007_12_2025.pdf","teerthanker mahaveer university|||btech cse in cloud technology and information security":"https://www.tmu.ac.in/programme/btech-cse-cloud-technology-information-security","the apollo university|||b. tech computer science and engineering (cyber security)":"https://apollouniversity.edu.in/admissions/fee-structure/b-tech-cse-cyber-security/","aryavart international university|||bca cloud technology & information security":"https://aiuniversity.edu.in/course_details.php?id=10","the lnm institute of information technology|||m.tech cse specialization in cybersecurity":"https://lnmiit.ac.in/admissions/pg-engineering/","the northcap university|||m.tech cse  cyber security and forensics":"https://www.ncuindia.edu/fee-structure/","tilak maharashtra vidyapeeth|||diploma in cyber forensics":"https://www.tmv.edu.in/DeptSkill/frmCyberSecurity.aspx?val=3","dr. vishwanath karad mit world peace university|||m.tech computer science and engineering (cyber security)":"https://mitwpu.edu.in/programme/mtech-computer-science-and-engineering-cyber-security","university of petroleum and energy studies|||b.tech computer science and engineering- cyber security and digital forensics":"https://drive.google.com/file/d/14TuI8KCZHgUi30qL_jBKJ6LxI3J_dZW8/view?usp=sharing","uttarakhand open university|||master of science (cyber security)":"https://uou.ac.in/sites/default/files/announcement-2019-07/Post-Graduate-Programme-Details-2019-2020.pdf","vels institute of science technology & advanced studies (vistas)|||b.sc computer science with specialisation in cybersecurity":"https://vistas.ac.in/school-of-computing-sciences-fees-structure/","visvesvaraya technological university|||mca in cyber security & cloud computing":"https://drive.google.com/file/d/1jbfwzWOsbpfD3OL_clpnkm1mAYFoyxFI/view?usp=drive_link","vellore institute of technology bhopal|||b.tech cse (cyber security & digital forensics)":"https://vitbhopal.ac.in/b-tech-fees/","vellore institute of technology bhopal|||b.tech with integrated m.tech cse (cyber security)":"https://drive.google.com/file/d/1-XYvZlg7yblN8siHvowA7MDqYvaVwxmT/view?usp=drive_link","vellore institute of technology bhopal|||m.tech. cse (cyber security & digital forensics)":"https://drive.google.com/file/d/1-XYvZlg7yblN8siHvowA7MDqYvaVwxmT/view?usp=drive_link","vellore institute of technology vellore|||m. tech. computer science and engineering (cyber security)":"https://drive.google.com/file/d/1-XYvZlg7yblN8siHvowA7MDqYvaVwxmT/view?usp=drive_link","vivekananda global university|||b.tech  cloud technology & cyber security":"https://vgu.ac.in/admission/fee-structure","vivekananda global university|||m.sc. digital and cyber forensic":"https://vgu.ac.in/admission/fee-structure","vivekananda global university|||mca  cloud technology & cyber securit":"https://vgu.ac.in/admission/fee-structure","yenepoya university|||b.tech computer science and engineering - cyber security":"https://drive.google.com/file/d/1bL9X91InK8fFzYuwkhzzNQV7weVWqlxO/view?usp=sharing","uttaranchal university|||bachelor of computer applications (bca) cyber security":"https://www.uudoon.in/computing-sciences/includes/fees/download/BCA-3-Years.pdf","uttaranchal university|||b.tech. (hons.) cse with specialization in cyber security":"https://www.uudoon.in/engineering/includes/fees/download/B.Tech.%20(Hons.)-CSE-Cyber-Security-4-YEAR.pdf","geeta university|||b.tech. (h) cse  cyber security":"https://drive.google.com/file/d/11xfFahXpNP5rDbwtvf_2mpOAI9xAjl9I/view?usp=sharing","geeta university|||bca in cyber security":"https://drive.google.com/file/d/11xfFahXpNP5rDbwtvf_2mpOAI9xAjl9I/view?usp=sharing","sage university indore|||b.tech ct (hons.) cyber security & forensic with quickheal academy":"https://sageuniversity.in/assets/feestructure/feestructure29.pdf","shanmugha arts science technology & research academy (sastrat)|||m. tech. in cyber security":"https://drive.google.com/file/d/1zRpXfnv-KUIV_HJimkv2Ex5s70ydZCwv/view?usp=sharing","shanmugha arts science technology & research academy (sastrat)|||b. tech. in computer science & engineering (specialization in cyber security and block chain technology)":"https://drive.google.com/file/d/1zRpXfnv-KUIV_HJimkv2Ex5s70ydZCwv/view?usp=sharing","national forensic sciences university guwahati|||b.tech - m.tech. computer science & engineering (cyber security)":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national forensic sciences university gandhinagar|||mba cyber security management":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national forensic sciences university gandhinagar|||professional diploma in cyber law":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national forensic sciences university delhi|||b.tech - m.tech. computer science & engineering (cyber security)":"https://beta.nfsu.ac.in/data/pdfs/admission/Programme%20Details.pdf","national institute of technology patna|||b.tech and m.tech dual degree (computer science and engineering with specialization in cyber security)":"https://drive.google.com/file/d/1MhS_UIYkOF2G3h0ms_kk8ZRjidr0IvGZ/view","indian institute of information technology senapati, manipur|||btech in computer science & engineering with specialization in cyber security":"https://iiitmanipur.ac.in/pages/academic/admission2025/FeeStructureIIITM2025.pdf","central university of jammu|||b. tech. cse (cyber security)":"https://www.cujammu.ac.in/media/departments/CSE/events/200525_Top_B._Tech.__Fee_2025-26.pdf","national institute of electronics and information technology ajmer|||b.tech in computer science and engineering (internet of things, cyber security including block chain technology )":"https://nielit.ac.in/fee-structure.php","malaviya national institute of technology, jaipur|||m. tech. program in computer science & information security":"https://mnit.ac.in/cms/uploads/2026/05/Fee_PG_2026-27.pdf","maulana azad national institute of technology bhopal|||m. tech. in cse with specialization in information security":"https://www.manit.ac.in/sites/default/files/addmissionsection/All_Fee_Structure_For_Session_2026_27.pdf","national institute of technology rourkela|||m.tech cse (information security)":"https://www.nitrkl.ac.in/docs/Announcement/12062021164923613.pdf","indian institute of information technology allahbad|||m.tech. it with specialization in network and security group":"https://aaa.iiita.ac.in/PDF1/M.Tech%20Fee%20Structure%20Jul-Dec%202025_2.pdf","punjab engineering college, chandigarh|||m.tech computer science & information security":"https://pec.ac.in/sites/default/files/2022-02/mtech_fee_structure_21-22.pdf","defence institute of advanced technology, girinagar, pune|||m.tech in cyber security":"https://diat.ac.in/wp-content/uploads/2026/07/M.Tech-New-1-Fee-structure-2026-27.pdf","dr. b r ambedkar national institute of technology, jalandhar|||m.tech computer science & engineering (information security)":"https://v1.nitj.ac.in/nitj_files/student_corner/Fee_structure_of_B_21112636448.pdf","heritage institute of technology (maulana abul kalam azad university of technology)|||b.tech computer science & engineering (internet of things and cyber security including block chain technology)":"https://www.heritageit.edu/PDF/BTech_2025_2026.pdf","techno main salt lake, sector-v, salt lake (maulana abul kalam azad university of technology)|||b.tech - cse - cyber security":"https://wbjeeb.in/assets/ALPG/PVTENGG/TECMAIN.pdf","dr.sudhir chandra sur institute of technology and sports complex (maulana abul kalam azad university of technology)|||b.tech computer science & engineering (cyber security)":"https://www.surtech.edu.in/fees-structure.php","guru nanak institute of technology, panihati, sodepur (maulana abul kalam azad university of technology)|||b.tech computer science & engineering (cyber security)":"https://gnit.ac.in/wp-content/uploads/2024/04/Course-Fee-All-course-2024.pdf","dr. b. c. roy engineering college, durgapur (maulana abul kalam azad university of technology)|||b.tech computer science & engineering (cyber security)":"https://bcrec.ac.in/public/storage/downloads/manager/B_Tech_Fee_Final_Fee_Structure.pdf","techno international new town, rajarhat, new town (maulana abul kalam azad university of technology)|||b.tech computer science & engineering (cyber security)":"https://tint.edu.in/downloads.html?task=download.send&id=141&catid=12&m=0","future institute of technology, boral, garia (maulana abul kalam azad university of technology)|||b.tech computer science & engineering (internet of things and cyber security including block chain technology)":"https://futureeducation.in/fit/index.php?option=com_content&view=article&id=8&Itemid=0","asansol engineering college (maulana abul kalam azad university of technology)|||b.tech computer science & engineering (internet of things and cyber security including block chain technology)":"https://aecwb.edu.in/academics/fee/aecFeeStruct2021_22.pdf","sister nivedita university, new town (maulana abul kalam azad university of technology)|||b.tech computer science & engineering (cyber security)":"https://www.snuniv.ac.in/fees-structure.aspx","rungta international university|||b.tech - cse - cyber security":"https://rungta.ac.in/fees","kristu jayanti university|||post graduate diploma in cyber law and cyber security":"https://drive.google.com/file/d/1QwtnexpF48byeva1pVwdzKUBS3U3vxc2/view?usp=sharing","galgotias university|||m.c.a. (industry oriented specialization in computer network & cyber security)":"https://drive.google.com/file/d/1xbXumzIzR641zrZEQEr6P3j2sPkydqpi/view?usp=sharing","galgotias university|||b.sc. (hons. with research) computer science (cyber security)":"https://drive.google.com/file/d/1xbXumzIzR641zrZEQEr6P3j2sPkydqpi/view?usp=sharing","galgotias university|||m.tech in computer science and engineering (cyber security)":"https://drive.google.com/file/d/1xbXumzIzR641zrZEQEr6P3j2sPkydqpi/view?usp=sharing","galgotias university|||b.c.a. in industry oriented specialization (computer networks and cyber security)":"https://drive.google.com/file/d/1xbXumzIzR641zrZEQEr6P3j2sPkydqpi/view?usp=sharing","sandip university nashik|||m.tech in cloud technology and information security":"https://www.sandipuniversity.edu.in/fees-structure.php","galgotias university|||post-graduate diploma in cyber and digital forensics":"https://drive.google.com/file/d/1xbXumzIzR641zrZEQEr6P3j2sPkydqpi/view?usp=sharing","guru gobind singh indraprastha university|||post graduate diploma in cyber security, cyber disaster and blockchain technology":"https://ipu.ac.in/adm2026/adm2026br/br280126ugprg/ch14.pdf","indian institute of technology hyderabad|||m.tech in networks and information security":"https://iith.ac.in/academics/assets/files/fee/2025/IITH-Fee-Structure-for-Jul-Dec-2025-Semester_Newly-Enrolled-Students.pdf","thakur college of engineering and technology, kandivali, mumbai (mumbai university)|||b.e. computer science and engineering (cyber security)":"https://www.tcetmumbai.in/fra-fees-structure.html","s.i.e.s. graduate school of technology, nerul, navi mumbai (mumbai university)|||b.e. computer science and engineering (internet of things and cyber security including block chain technology)":"https://siesgst.edu.in/images/Fee%20structure.pdf","g. h. raisoni college of engineering nagpur (rashtrasant tukadoji maharaj nagpur university)|||b. tech computer science and engineering (cyber security)":"https://ghrcemn.raisoni.net/fees-structure","st. vincent pallotti college of engineering & technology, nagpur (rashtrasant tukadoji maharaj nagpur university)|||b.tech - computer science & engineering (cyber security)":"https://www.stvincentngp.edu.in/admissions","annasaheb dange college of engineering and technology, ashta, sangli (shivaji university)|||b.tech cse(iot and cyber security including block chain technology)":"https://www.adcet.ac.in/fee-structure","tatyasaheb kore institute of engineering and technology, yelur (shivaji university)|||b.tech in cyber security":"https://tkietwarana.ac.in/upload/admission/Admission%20Data/25-26%20FEE%20STRUCTURE%20FOR%20ACADEMIC%20YEAR%202025-26.pdf","jawahar education society's annasaheb chudaman patil college of engineering,kharghar, navi mumbai (mumbai university)|||b.tech computer science & engineering (internet of things and cyber security including block chain technology)":"https://acpce.ac.in/wp-content/uploads/2025/08/FE.pdf","mh sabao sidik college of engineering ( mumbai university)|||b.tech computer science & engineering (internet of things and cyber security including block chain technology)":"https://anjumaniislam.in/intake/","smt. indira gandhi college of engineering, navi mumbai (mumbai university)|||b.tech computer science & engineering (internet of things and cyber security including block chain technology)":"https://sigce.edu.in/wp-content/uploads/2024/08/fee-structure-2024-25.pdf","hope foundation and research center's finolex academy of management and technology, ratnagiri (mumbai university)|||b.tech computer science and engineering (cyber security)":"https://drive.google.com/file/d/1ea1fjhSM8JR3OLFRViyu5ES8E4oqanne/view","xavier institute of engineering c/o xavier technical institute,mahim,mumbai (mumbai university)|||b.tech computer science & engineering (internet of things and cyber security including block chain technology)":"https://www.xavier.ac.in/pdf/Fee%20Structure%2026-27.pdf","yadavrao tasgaonkar college of engineering & management (mumbai university)|||b.tech in cyber security":"https://ytcem.com/admission/fees-structure/","dilkap research institute of engineering and management studies (mumbai university)|||b.tech computer science & engineering (internet of things and cyber security including block chain technology)":"https://driems.in/wp-content/uploads/2024/06/Fees-Structure-2024-25.pdf","shri guru gobind singhji institute of engineering and technology, nanded (swami ramanand teerth marathwada university)|||m.tech computer networks and information security":"https://sggs.ac.in/source/Admissions/admission%202022-23/fee%20str/updated%20mtech%201st%20yer.pdf","s.i.e.s. graduate school of technology, nerul, navi mumbai (mumbai university)|||m.e information security":"https://siesgst.edu.in/images/Fee%20structure.pdf","chhotubhai gopalbhai patel institute of technology, maliba campus, bardoli (uka tarsadia university)|||b.tech computer science and engineering (cyber security)":"https://www.utu.ac.in/download/Fees/2025-26/Institutewise%20Fee%20Structure%202025-26.pdf","itm vocational university, waghodia,vadodara|||b.tech in cyber security":"https://www.itm.ac.in/Images/fee/M-ME-CSE.pdf","swarrnim startup and innovation university|||b.tech in cyber security":"https://swarrnim.edu.in/swarrnim/documents/Appendix%2029.pdf","govt engg college w. champaran (bihar engineering university)|||b.tech computer science and engineering (cyber security)":"https://www.gecwc.ac.in/wp-content/uploads/sites/34/2023/10/Expenditure-details-for-Regular-Students-Upto-22-Batch.pdf","shri shankaracharya technical campus, bhilai (chhattisgarh swami vivekanand technical university)|||b.tech computer science & engineering (internet of things and cyber security including block chain technology)":"https://sstc.ac.in/fee_structure","atme college of engineering, mysore  (visvesvaraya technological university)|||be cse  cyber security":"https://atme.edu.in/__l5e/assets-v1/03f673b7-5e9f-4f56-9e8c-a85c80057bb3/Fees-structure-2025-26.pdf","b m s college of engineering, basavanagudi (visvesvaraya technological university)|||be computer science and engineering (iot and cybersecurity including blockchain)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","acs college of engineering, mysore road (visvesvaraya technological university)|||be cse  cyber security":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","akash intitute of engineering and technology (visvesvaraya technological university)|||be cse (cyber security)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","alva's institute of engineering & technology, moodabidre, d.k (visvesvaraya technological university)|||be computer science and engineering (iot and cybersecurity including blockchain)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","aps college of engineering, somanahalli, bangalore (visvesvaraya technological university)|||be cse (cyber security)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","bangalore institute of technology, k.r.road, bangalore (visvesvaraya technological university)|||be cse (iot & cyber security including blockchain technology)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","bheemanna khandre institute of technology, bhalki (visvesvaraya technological university)|||be cse (cyber security)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","brindavan college of engineering, yelahanaka, bangalore (visvesvaraya technological university)|||be cse (iot & cyber security including blockchain technology)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","cambridge institute of technology, north campus, devanahalli, bangalore (visvesvaraya technological university)|||be cse (cyber security)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","cambridge institutute of technology, k.r.puram, bangalore (visvesvaraya technological university)|||be cse (iot & cyber security including blockchain technology)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","coorg institute of technology, kunda, ponnampet (visvesvaraya technological university)|||be cse (cyber security)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","dayananda sagar academy of technology & management technical campus (visvesvaraya technological university)|||be cse (cyber security)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","dayananda sagar academy of technology & management technical campus (visvesvaraya technological university)|||be cse (iot & cyber security including blockchain technology)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","east point college of engineering & technology, bangalore (visvesvaraya technological university)|||be cse (iot & cyber security including blockchain technology)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","east west institute of technology (visvesvaraya technological university)|||be cse (iot & cyber security including blockchain technology)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","impact college of engineering & applied sciences, bangalore (visvesvaraya technological university)|||be cse (cyber security)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","k. s. institute of technology  (visvesvaraya technological university)|||be cse (iot & cyber security including blockchain technology)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","m s ramaiah institute of technology, bangalore (visvesvaraya technological university)|||be cse (cyber security)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","maharaja institute of technology mysore,belawadi,srirangapatna,mandya (visvesvaraya technological university)|||be cse (iot & cyber security including blockchain technology)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","mangalore institute of technology & engineering, moodabidri, mangalore (visvesvaraya technological university)|||be cse (iot & cyber security including blockchain technology)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","rajarajeswari college of engineering, bangalore (visvesvaraya technological university)|||be cse (iot & cyber security including blockchain technology)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","rns institute of technology, bangalore (visvesvaraya technological university)|||be cse (cyber security)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","s e a college of engineering & technology, virgonagar, bangalore (visvesvaraya technological university)|||be cse (iot & cyber security including blockchain technology)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","sambhram institute of technology, bangalore (visvesvaraya technological university)|||be cse (cyber security)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","sir m.visveswaraya institute of technology, bangalore  (visvesvaraya technological university)|||be cse (iot & cyber security including blockchain technology)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","sri venkateshwara college of engineering, bangalore (visvesvaraya technological university)|||be cse (cyber security)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","t.john institute of technology, bangalore (visvesvaraya technological university)|||be cse (iot & cyber security including blockchain technology)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","a j institute of engineering and technology.kottar chowki boloor village mangalore (visvesvaraya technological university)|||be cse (iot & cyber security including blockchain technology)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","gurunanak dev engineering college, bidar (visvesvaraya technological university)|||be cse (iot & cyber security including blockchain technology)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","p a college of engineering, kairangal, bantwala tq,. mangalore (visvesvaraya technological university)|||be cse (iot & cyber security including blockchain technology)":"https://drive.google.com/file/d/1rdC7GBkH0w9zhAf2amRYlhGy3XpyonNb/view?usp=sharing","gm university|||b.tech in computer science- cyber security":"https://gmu.ac.in/admission-card/","gm university|||b.tech in computer science-information security":"https://gmu.ac.in/admission-card/","mes- m e s college of engineering, kuttippuram (a.p.j. abdul kalam technological university)|||b.tech in computer science & engineering (cyber security)":"https://mesce.ac.in/documents/Mandatory-Disclosures-2022.pdf","vimal jyothi engineering college|||b.tech in computer science & engineering (cyber security)":"https://vjec.ac.in/public/files/vjec_prospectus_23.pdf","jyothi engineering college, thrissur (a.p.j. abdul kalam technological university)|||b.tech in computer science & engineering (cyber security)":"https://www.jecc.ac.in/Home/jechome_admin/assets/policy_doc/JECC_MandatoryDisclosure.pdf","college of engineering, kallooppara, thiruvalla (a.p.j. abdul kalam technological university)|||post graduate diploma in cyber forensics & security":"https://drive.google.com/file/d/1euv8yIF_f215XRzYEzhvr10Owpl6rJXf/view","providence college of engineering, chengannur (a.p.j. abdul kalam technological university)|||btech in computer science & engineering (cyber security, iot & blockchain technology)":"https://drive.google.com/file/d/1EY9ylKSzDHgDvicAs2cqpXzMzOAeLiJO/view","university college of engineering,thodupuzha  (a.p.j. abdul kalam technological university)|||b.tech in computer science & engineering (cyber security)":"https://ucet.ac.in/details?cmsid=109&tag=Admissions","al-azhar college of engineering and technology, idukki  (a.p.j. abdul kalam technological university)|||b.tech in computer science & engineering (cyber security)":"https://engineering.alazharthodupuzha.org/wp-content/uploads/2024/04/mandatory-disclosure.pdf","al-ameen engineering college, palakkad (a.p.j. abdul kalam technological university)|||b.tech in computer science & engineering (cyber security)":"https://alameen.edu.in/wp-content/uploads/2022/11/Mandatory-Disclosure.pdf","aalim muhammed salegh college of engineering (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","s.a engineering college, chennai (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1fSh8Tf1-Rav4wG55YjSTJWmsR2nXtVJa/view","sri venkateswara college of engineering and technology, thirupachur (anna university)|||be cse (cyber security)":"https://www.svce.ac.in/wp-content/uploads/2025/07/UG-first-year-DOTE-fees.pdf","university college of engineering villupuram|||be cse (cyber security)":"https://aucev.edu.in/wp-content/uploads/2026/05/UCEV-Fees-Structure-2025-26.pdf","university college of engineering kancheepuram|||be cse (cyber security)":"http://www.aucek.in/assets/ucekfee-str/FEESTRUCTUREUCEK.pdf","rajadhani institute of science and technology, palakkad (a.p.j. abdul kalam technological university)|||b.tech in computer science & engineering (cyber security)":"https://www.rist.edu.in/mandatory-disclosure/","ilahia college of engineering and technology, ernakulam (a.p.j. abdul kalam technological university)|||b.tech in computer science & engineering (cyber security)":"https://icet.ac.in/under-graduate-admission/","kmct institute of emerging technology and management, mukkam, kozhikode (a.p.j. abdul kalam technological university)|||b.tech in computer science & engineering (cyber security)":"https://drive.google.com/file/d/1wZEfck_JPbWRzx1aWGfKwfKMgsTzfVQl/view?usp=drive_link","royal college of engineering and technology, thrissur (a.p.j. abdul kalam technological university)|||b.tech in computer science & engineering (cyber security)":"https://royalcet.ac.in/wp-content/uploads/2024/08/fee.pdf","st josephs college of engineering and technology, palai (a.p.j. abdul kalam technological university)|||b.tech in computer science & engineering (cyber security)":"https://drive.google.com/file/d/1Y-OGRHRXEBlOHDunsBQq--6g5AyNKZyO/view?usp=sharing","sree narayana gurukulam college of engineering, ernakulam (a.p.j. abdul kalam technological university)|||b.tech in computer science & engineering (cyber security)":"https://drive.google.com/file/d/1swlsX7rI3qodI5GIE4Z0OTP_vYuor43b/view?usp=sharing","ukf college of engineering and technology, kollam (a.p.j. abdul kalam technological university)|||b.tech in computer science & engineering (cyber security)":"https://drive.google.com/file/d/1Q0BWJ-BuMYhSqsytA5Uigpe3ZyQc6BIY/view?usp=drive_link","velammal engineering college (autonomous), velammal nagar, ambattur (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","sri venkateswara institute of science and technology, kolundhalur (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","r.m.k. college of engineering and technology (autonomous), thiruvallur (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","mohamed sathak a j college of engineering (autonomous) (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","anand institute of higher technology(autonomous), (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","jerusalem college of engineering (autonomous), pallikkaranai (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","kcg college of technology (autonomous), karapakkam (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","t.j. institute of technology, rajiv gandhi salai, karapakkam (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","st. joseph college of engineering, trinity campus (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","chennai institute of technology (autonomous) (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","sri sai ram engineering college (autonomous), sai leo nagar|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","tagore engineering college, rathinamangalam (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","mgm college of engineering and technology, pampakuda|||b.tech in computer science & engineering (cyber security)":"https://drive.google.com/file/d/1L39S_c-8lVlSnTb39CTUuI0ajUtU7Mtw/view?usp=sharing","jitendra chauhan law college, vile parle (mumbai university)|||pg diploma in cyber law & it":"https://pgcl.ac.in/wp-content/uploads/2025/07/Cyber-Law-Brochure.pdf","gojan school of business and technology, thiruvallur (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","sree sastha institute of engineering and technology chembarambakkam (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","p.b. college of engineering kancheepuram (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","st. lourdes engineering college sadhananthapuram (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","dhanalakshmi srinivasan college of engineering and technology, kanchipuram (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","mahalakshmi tech campus chrompet (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","prathyusha engineering college (autonomous) (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","sriram engineering college, perumalpattu, veppampattu (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","vel tech multi tech dr rangarajan dr sakunthala engineering college (autonomous)  (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","sams college of engineering and technology, 82,panapakkam, tirupathi road  (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","jnn institute of engineering (autonomous), thiruvallur  (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","st. joseph's institute of technology (autonomous), jeppiaar kanchipuram (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","madras engineering college, tambaram road, kanchipuram - 602105. (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","rajalakshmi engineering college (autonomous), kanchipuram, chennai-602105. (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","saveetha engineering college (autonomous), saveetha nagar, kancheepuram (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","university of petroleum and energy studies|||ll.m. cyber security and digital laws":"https://drive.google.com/file/d/14TuI8KCZHgUi30qL_jBKJ6LxI3J_dZW8/view?usp=sharing","maharishi paetanjali polytechnic of infomaetin tecnology ,karnelganj,|||pg diploma in cyber security":"https://mpit.co.in/fee.aspx","maharashtara national law university|||post graduate diploma in cyber laws and artificial intelligence":"https://www.nlunagpur.ac.in/PDF/2023/Short%20Advertisement-1.pdf","hindi vidya prachar samiti's college of law (mumbai university)|||post graduate diploma in cyber law":"https://www.hvpslawcollege.edu.in/wp-content/uploads/2024/06/Cyber-2021-22_Course-Design.pdf","easwari engineering college (autonomous), bharathi salai, ramapuram, chennai-600089. (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","g k m college of engineering and technology, g k m nagar (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","ifet college of engineering (autonomous), ifet nagar (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","sri venkateswaraa college of technology(autonomous) (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","jaya sakthi engineering college, st.mary's nagar, thiruninravur (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","asan memorial college of engineering and technology (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","new prince shri bhavani college of engineering and technology (autonomous) (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","surya group of institutions, nh-45, gst road, vikiravandi, villupuram-605652. (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","prince dr. k. vasudevan college of engineering and technology (autonomous) (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","peri institute of technology (autonomous), mannivakkam,tambaram, kancheepuram (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","adhiparasakthi college of engineering, g.b.nagar, kalavai, arcot (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","arunai engineering college (autonomous), chittor-cuddalore (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","s.k.p. engineering college, chinnkangiyanur, somasipadi post (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","sri shanmugha college of engineering and technology (autonomous) (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","dhaanish ahmed institute of technology, pitchanur village, coimbatore-641018 (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","arjun college of technology, 310/1b, chettiyakkapalayam (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","cheran college of technology, cheran nagar, thittuparai, kangeyam, tiruppur-638701. (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","dr. subhash university, school of engineering & technology, junagadh|||b.tech  computer science engineering with cyber security":"https://drive.google.com/file/d/1FRB8MxnfqQYEI53i9ReVre8rE167Khzc/view?usp=drive_link","shree dhanvantary college of engineering & technology, kim (gujarat technological university)|||b.tech computer science engineering (internet of things and cyber security including block chain technology)":"https://sdcet.org.in/pdf/sdcde_mandatory_disclosure_2021-22.pdf","vidhyadeep university|||b.tech computer science and engineering (cyber security)":"https://vidhyadeepuni.ac.in/fees-structure.php","jawaharlal institute of technology, borawan, khargone (rajiv gandhi proudyogiki vishwavidyalaya)|||b.tech computer science and engineering (cyber security)":"https://jitechno.com/Fee-Structure.html","nri institute of research technology (rajiv gandhi proudyogiki vishwavidyalaya)|||b.tech computer science and engineering (cyber security)":"https://www.nrigroupindia.com/wp-content/uploads/2020/04/nirt-course-detail.pdf","rathinam technical campus|||b.tech computer science & engineering (cybersecurity)":"https://rathinamcollege.in/fee-structure/","government college of engineering (autonomous) bargur krishnagiri district 635104 (anna university)|||b.tech computer science & engineering (cybersecurity)":"https://gcebargur.ac.in/sites/gcebargur.ac.in/files/Fees/Fee%20structure%202025-26.pdf","government polytechnic , kudligi|||diploma cyber physical systems and security":"https://gpt.karnataka.gov.in/gptkudligi/public/uploads/174_gpt_kudligi_mandatory_details%20112_1773651328.pdf","gaya college of engineering|||m. tech. in cyber security":"https://www.gcegaya.ac.in/wp-content/uploads/2025/05/Fee-Structure.pdf","vikrant institute of technology & management indore (rajiv gandhi proudyogiki vishwavidyalaya)|||m. tech. in cyber security":"https://vitmindore.com/Fees_Submission.html","sree narayana gurukulam college of engineering (a.p.j. abdul kalam technological university)|||m.tech cse (cyber security)":"https://www.sngce.ac.in/MTech-Fees-Structure2022.pdf","government engineering college, wayanad (a.p.j. abdul kalam technological university)|||m tech in computer science and engineering (network and security)":"https://drive.google.com/file/d/1MVZMycqZVcbwgjS4iD5tkS269m3w1Pcw/view","lbs college of engineering, muliyar,kasaragod (a.p.j. abdul kalam technological university)|||m.tech in computer science and information security":"https://lbscek.ac.in/wp-content/uploads/2025/07/MTechFee2025.pdf","b.m.s.institute of technology and management (visvesvaraya technological university)|||m. tech. cyber security":"https://bmsit.ac.in/pdfs/2026-27-fees.pdf","bapuji institute of engineering & technology (visvesvaraya technological university)|||m. tech. cyber security":"https://drive.google.com/file/d/1NwN1abZ2nEGtFujFJm-4NRIoyZHgWl68/view","ganpat university|||master of science in information technology (cyber security)":"https://www.ganpatuniversity.ac.in/programmes/after-graduation-pg-programs/computer-applications/master-of-science-in-information-technology-cyber-security","indian institute of technology jodhpur|||mba in fintech & cybersecurity":"https://iitj.ac.in/PageImages/Gallery/03-2025/fee-structure-202425-638780609512096806.pdf","international institute of business studies banglore|||post graduate diploma in cyber security":"https://www.iibsonline.com/admissions/admission-fee-structure","b. s. abdur rahman crescent institute of science and technology|||b.tech. computer science and engineering (cyber security)":"https://crescent.education/wp-content/uploads/2023/05/CRESCENT-MANDATORY-DISCLOSURE-FEBRUARY2022.pdf","mahendra engineering college (autonomous), mahendhirapuri, mallasamudram west (anna university)|||be cyber security":"https://drive.google.com/file/d/1vog0rWXRzF2SF33kPUkXoESePa2Hb8wr/view","paavai engineering college (autonomous), nh-7, paavai nagar, pachal, namakkal-637018. (anna university)|||be cyber security":"https://drive.google.com/file/d/1vog0rWXRzF2SF33kPUkXoESePa2Hb8wr/view","k s r college of engineering (autonomous) (anna university)|||be cse (cyber security)":"https://drive.google.com/file/d/1vog0rWXRzF2SF33kPUkXoESePa2Hb8wr/view","c. v. raman global university|||m.sc. in cs & it (iot & cyber security)":"https://cgu-odisha.ac.in/fee-structure/","cochin university of science and technology|||m.tech in computer science and engineering with specialization in cyber security":"https://admissions.cusat.ac.in/Prospectus/Fee_Structure2026.pdf","dr. d. y. patil arts, commerce & science college, pimpri, pune (savitribhai phule pune university)|||m.sc. (cyber security)":"https://acs.dypvp.edu.in/document/PG-Course-fee.pdf","school of technology and applied sciences pullarikunnu (stas) (mahatma gandhi university)|||msc cyber forensics":"https://stasktm.cpas.ac.in/courses/14","toms college of engineering (mahatma gandhi university)|||bsc cyber forensics":"https://eeconfigstaticfiles.blob.core.windows.net/staticfiles/tomscollege/ee-form-widget/Arts%20and%20college.pdf","toms college of engineering|||diploma cyber forensic and information security (cs)":"https://eeconfigstaticfiles.blob.core.windows.net/staticfiles/tomscollege/ee-form-widget/Polytechnic.pdf","university of petroleum and energy studies|||b.sc. computer science cyber security & forensics":"https://drive.google.com/file/d/14TuI8KCZHgUi30qL_jBKJ6LxI3J_dZW8/view?usp=sharing","bharata mata college of commerce &arts ,chunangamvely,aluva (mahatma gandhi university)|||b.sc (hons) cyber forensic":"https://cap.mgu.ac.in/collegeinfo/fees_view_unaided.jsp","bishop vayalil memorial holy cross college, cherpunkal (mahatma gandhi university)|||b.sc cyber forensics":"https://bvmcollege.com/academics/ug/ug-fee-structure/","avs college of arts & science attur main road, ramalingapuram,|||bachelor of science in cyber security":"https://www.avscollege.ac.in/pdf/fees.pdf","cochin arts and science college,manakkakadavu (mahatma gandhi university)|||b.sc cyber forensics":"https://drive.google.com/file/d/1N-OzlaF54LjBwL9nIraU6jsu2qX0voyv/view?usp=sharing","girideepam institute of advanced learning, vadavathoor (mahatma gandhi university)|||b.sc cyber forensics":"https://girideepamcollege.ac.in/web/fetchFeeStructure","kmm college of arts & science, thrikkakara (mahatma gandhi university)|||b.sc cyber forensics":"https://cap.mgu.ac.in/collegeinfo/fees_view_unaided.jsp","kmm college of arts & science, thrikkakara (mahatma gandhi university)|||msc cyber forensics":"https://cap.mgu.ac.in/collegeinfo/pgfees_view_unaided.jsp","kristu jyoti college of management & technology, kurisummoodu p.o, changanacherry (mahatma gandhi university)|||bsc. (hons) cyber forensics":"https://kjcmt.ac.in/merit-seat-tuition-fee/","swamy saswathikananda college, poothotta p.o, ernakulam (mahatma gandhi university)|||bsc cyber forensics  network security":"https://cap.mgu.ac.in/collegeinfo/fees_view_unaided.jsp","children welfare centre's college of law (mumbai university)|||post graduate diploma in cyber law and information technology":"https://www.cwclawcollege.in/feestructure.php","vasant dada patil pratishtan's law college (mumbai university)|||post graduate diploma in cyber law":"https://vpplc.in/assets/docs/Circular-%20Fees%20for%20Academic%20Year%202025-2026.pdf","vidyaa vikas college of engineering and technology (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","cms college of engineering, cms nagar, eranapuram post, namakkal-637003. (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","r p sarathy institute of technology (autonomous) , poosaripatty(po), omalur taluk, salem-636305. (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","p.s.v.college of engineering and technology, mittapalli, balinayanapalli post, krishnagiri-635108. (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","kangeyam institute of technology (autonomous) (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","sree sakthi engineering college (autonomous), bettathapuram, bilichi village (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","coimbatore institute of engineering and technology (autonomous), vellimalaipattinam, narasipuram post, (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","dr mahalingam college of engineering and technology (autonomous) (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","erode sengunthar engineering college (autonomous), thudupathi, perundurai (tk), erode district-638057. (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","hindusthan college of engineering and technology(autonomous), othakkalmandapam village (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","karpagam college of engineering (autonomous) (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","park college of engineering and technology (autonomous)  (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","sri shakthi institute of engineering and technology|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1HbY1649UrWVg2pySFdSwtMYWqjs6vI5t/view?usp=sharing","dr n.g.p. institute of technology (autonomous), dr. n.g.p. nagar, kalapatti road, coimbatore-641048.  (anna university)|||b.e. computer science and engineering [cyber security]":"https://www.drngpit.ac.in/assets/pdf/fees-structure.pdf","sri sai ranganathan engineering college (autonomous) , viraliyur post, thondamuthur(via), coimbatore-641109. (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","sri eshwar college of engineering (autonomous), kondampatti post, vadasithur via, coimbatore-641202. (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","dhanalakshmi srinivasan college of engineering (cbe) (autonomous), coimbatore-641105. (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","surya engineering college, perundurai road,manalmedu, mettukadai,kathirampatti post, erode-638107. (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","easa college of engineering and technology (autonomous), coimbatore-641105. (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","kalaignarkarunanidhi institute of technology (autonomous) (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","sudharsan engineering college, sathiyamangalam, kulathur taluk, pudukkottai district-622501. (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","thamirabharani engineering college (autonomous) (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","aaa college of engineering and technology, amathur village, sivakasi, virudhunagar-626123. (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","sethu institute of technology (autonomous), pulloor, kariapatti, virudhunagar-626115. (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","immanuel arasar jj college of engineering, edavilagam, nattalam, marthandam, kanyakumari-629195. (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","unnamalai institute of technology, suba nagar, ayyaneri post, kovilpatti, thoothukudi district-628502. (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","nellai college of engineering , maruthakulam p.o, nanguneri taluk, tirunelveli-627151. (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","arul tharum vpmm college of engineering and technology (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","vins christian college of engineering, vins nagar, chunkankadai, nagercoil, kanyakumari-629807. (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","ssm institute of engineering and technology (autonomous) (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","n.p.r college of engineering and technology (autonomous) (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","srm madurai college for engineering and technology, pottapalayam village (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","veerammal engineering college, pvp nagar, k.singrakottai, dindigul-624708. (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","rvs school of engineering and technology (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","k.l.n.college of engineering (autonomous) (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","mohamed sathak engineering college (autonomous) (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","psna college of engineering and technology (autonomous) (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","p.t.r. college of engineering and technology (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","pandian saraswathi yadav engineering college, arasanoor village (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","fatima michael college of engineering and technology, senkottai village (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","school of information technology indira university|||b.sc - cyber security":"https://drive.google.com/file/d/1dQVtb00fg_oQQZKg26v1XSH9cJh0KTDh/view?usp=sharing","velammal college of engineering and technology (autonomous), velammal nagar, viraganoor (anna university)|||b.e. computer science and engineering [cyber security]":"https://drive.google.com/file/d/1W8qL3uqgH_w4mvrT0wetisjUUQ_KhJpx/view","arizona state university|||computer science (cybersecurity), bs":"https://admission.asu.edu/cost-aid/international","arizona state university|||computer science (cybersecurity), ms":"https://admission.asu.edu/cost-aid/international","arizona state university|||computer science (cybersecurity), mcs":"https://drive.google.com/file/d/1Hx8ra5eAhmLX6nZvgzn49suPaowUgU2K/view?usp=sharing","arizona state university|||master of arts in global security  cybersecurity":"https://drive.google.com/file/d/1Hx8ra5eAhmLX6nZvgzn49suPaowUgU2K/view?usp=sharing","auburn university|||master of science in cybersecurity engineering":"https://www.auburn.edu/academic/international/isss/cost.php","auburn university|||cybersecurity engineering graduate certificate":"https://bulletin.auburn.edu/generalinformation/financialinformation/basicchargesrevisedmay/","augusta university|||cybersecurity bachelor of science":"https://www.augusta.edu/tuition/undergraduate.php","brown university|||master of science in cybersecurity":"https://sfs.brown.edu/tuition-and-fees/graduate","bluefield university|||bs in cybersecurity":"https://drive.google.com/file/d/12SyaYMTxt293gEueTS_J1YM6gmnEt_UI/view?usp=sharing","california state university, dominguez hills|||m.s. in cybersecurity":"https://www.csudh.edu/financial-aid/cost/","capitol technology university|||bachelor of science (bs) in cybersecurity":"https://www.captechu.edu/admissions-and-financial-aid/international-students","cedarville university|||bachelor of science in cyber operations":"https://www.cedarville.edu/offices/cashiers/cost-information/undergraduate/online-undergraduate-cost-and-tuition","central connecticut state university|||cybersecurity bachelor of science":"https://www.ccsu.edu/tuition-aid","dominican university|||master of science in cybersecurity (msc)":"https://www.dom.edu/offices/student-accounts/tuition-fees-and-expenses","embry-riddle aeronautical university|||master of science in cyber intelligence and security":"https://erau.edu/admissions/tuition-and-costs#daytona-beach","embry-riddle aeronautical university|||bachelor of science in cyber intelligence and security":"https://erau.edu/admissions/tuition-and-costs#daytona-beach","fairfield university|||master of science in cybersecurity":"https://www.fairfield.edu/admission-and-aid/tuition-and-costs/graduate/","florida state university|||bs in cyber criminology":"https://tuition.fsu.edu/sites/g/files/upcbnu4416/files/Documents/2025-2026%20tuition/2025-2026_Tuition_Main.pdf","fordham university|||master of science in cybersecurity":"https://www.fordham.edu/student-financial-services/tuition-and-payments/graduate-tuition/graduate-school-of-arts-and-sciences/","fort hays state university|||master of professional studies in cybersecurity":"https://www.fhsu.edu/admissions/tuition/costofattendance","fort hays state university|||bachelors degree in cybersecurity":"https://www.fhsu.edu/admissions/tuition/costofattendance","guilford college|||bs cyber and network security major":"https://www.guilford.edu/admissions/financial-aid/tuition-and-fees","indiana university bloomington|||b.s. in cybersecurity and global policy":"https://studentcentral.indiana.edu/cost-of-iu/index.html#ugrad","kennesaw state university|||master of science in cybersecurity":"https://campus.kennesaw.edu/offices-services/fiscal-services/bursar/tuition-fees/docs/fy26-graduate-tuitionandfees.pdf","kennesaw state university|||bachelor of science in cybersecurity":"https://campus.kennesaw.edu/offices-services/fiscal-services/bursar/tuition-fees/docs/fy26-undergraduate-tuitionandfees.pdf","kent state university|||cybersecurity engineering - b.s.":"https://www.kent.edu/fbe-center/tuition-and-other-costs","miami university (ohio)|||bachelor of science in cybersecurity":"https://miamioh.edu/admission-aid/costs-financial-aid/cost-of-attendance.html","middle tennessee state university|||cybersecurity management, m.s.":"https://www.mtsu.edu/tuition/wp-content/uploads/sites/94/2025/06/25-26_Graduate.pdf","middle tennessee state university|||cybersecurity management, b.s":"https://www.mtsu.edu/tuition/wp-content/uploads/sites/94/2025/06/25-26_Undergraduate.pdf","mississippi state university|||b.s. cybersecurity":"https://www.sfa.msstate.edu/cost/24/ug","montana state university|||m.s. in cybersecurity":"https://www.montana.edu/international/admissions/cost.html","montclair state university|||cybersecurity (ms)":"https://www.montclair.edu/tuition-and-fees/graduate-costs/","new jersey institute of technology|||m.s. in cyber security and privacy":"https://www.njit.edu/admissions/tuition-costs","new york university|||ms cybersecurity":"https://steinhardt.nyu.edu/admissions/tuition-and-student-charges/graduate-study-tuition-and-fees","oakland university|||master of science in cyber security":"https://www.oakland.edu/financialaid/costs/tuition-rates/","oakland university|||bachelor of science in cybersecurity":"https://www.oakland.edu/financialaid/costs/tuition-rates/","purdue university|||master of science in computer science, concentration in information and cyber security":"https://www.purdue.edu/treasurer/finance/bursar-office/tuition/purdue-online-tuition-and-fees-2025-2026/college-of-science/","quinnipiac university|||ms cybersecurity":"https://drive.google.com/file/d/1T1BKtSqKCxGIZceQxGjiJ2XVPTq2xQK1/view?usp=sharing","robert morris university|||cybersecurity m.s.":"https://www.rmu.edu/admissions/student-financial-services/grad-tuition#masters","robert morris university|||cybersecurity b.s.":"https://www.rmu.edu/admissions/student-financial-services/undergrad-tuition#campus","rochester institute of technology (rit)|||ms cybersecurity":"https://www.rit.edu/admissions/tuition-and-fees","rochester institute of technology (rit)|||bs cybersecurity":"https://www.rit.edu/admissions/tuition-and-fees","rutgers university brunswick|||mbs cybersecurity":"https://grad.rutgers.edu/academics/graduate-programs/biomedical-health-sciences-masters-programs/mbs/tuition","sacred heart university|||master's in cybersecurity":"https://www.sacredheart.edu/offices--departments-directory/student-accounts/tuition--fees/graduate-tuition--fees-2025-2026/","sacred heart university|||bs in cybersecurity":"https://www.sacredheart.edu/offices--departments-directory/student-accounts/tuition--fees/full-time-undergraduate-tuition--fees-2025-2026/","saint leo university|||bachelor's degree in cybersecurity":"https://www.saintleo.edu/sites/default/files/2024-02/2024-2025%20Tuition%20and%20Fees-Campus%20Undergraduate%2001.26.24.pdf","saint peter's university|||m.s. in cybersecurity":"https://www.saintpeters.edu/enrollment-services/student-accounts/tuition-and-fees/","sam houston university|||cybersecurity, bachelor of science":"https://catalog.shsu.edu/undergraduate/financial-information/tuition-fees/","temple university|||cybersecurity b.s.":"https://payingforcollege.temple.edu/cost-attendance","troy university|||bachelor's degree in cyber security":"https://www.troy.edu/international/tuition-fees.html","university of alabama at birmingham|||m.s. in cyber security":"https://drive.google.com/file/d/1GPW0OpUjj_omAm1M2y8Z0CJ6VjtlDUsj/view?usp=drive_link","university of michigan|||ms cybersecurity":"https://ro.umich.edu/tuition-residency/tuition-fees?year=140&school=93&term_type=75&level=84","university of cincinnati|||cybersecurity bs":"https://www.uc.edu/about/international/admissions/cost.html","university of colorado denver|||bachelor of science in cybersecurity":"https://www.ucdenver.edu/tuition-cost","university of delaware|||m.s. cybersecurity":"https://drive.google.com/file/d/1ThTvbfrA8VKiULWwzeDEK8rxoMjQQw-v/view?usp=sharing","university of denver|||cybersecurity: master's degree":"https://www.du.edu/admission-aid/undergraduate/international-applicants/tuition","university of houston|||master of science in cybersecurity":"https://drive.google.com/file/d/1m3D-GEZwDUF_WnKlPOmsJXbwPSO3ODxm/view?usp=sharing","university of michigan|||bs cybersecurity":"https://admissions.umich.edu/costs-aid/costs","university of nebraska omaha|||bachelor of science in cybersecurity":"https://www.unomaha.edu/undergraduate-admissions/tuition-and-aid/estimated-cost-of-attendance.php#ug","university of nevada|||masters degree in cybersecurity":"https://www.unr.edu/grad/funding/tuition-and-fees/international-cost-no-ga","university of new haven|||bachelor of science in cybersecurity":"https://www.newhaven.edu/about/departments/bursars/tuition/undergraduate-2025-2026.php","university of north carolina greensboro|||cybersecurity, b.s.":"https://spartancentral.uncg.edu/financial-aid/cost-of-attendance/","university of north texas|||m.s. in cybersecurity":"https://estimatemytuition.unt.edu/results.html?year=2025&residency=INTL&degree_level=Masters&location=multiple&major=Cybersecurity+MS&hours=1","university of north texas|||b.s. cybersecurity":"https://estimatemytuition.unt.edu/results.html?year=2025&residency=INTL&degree_level=Bachelors&location=multiple&major=Cybersecurity&hours=1","the university of oklahoma|||bachelor of science: cybersecurity":"https://www.ou.edu/bursar/tuition_fees","university of texas at dallas|||master of science in cyber security, technology and policy":"https://drive.google.com/file/d/1wvZv-Sp8pro0GZORcP5ljFe_N9owJE6T/view?usp=sharing","university of toledo|||master of science in cybersecurity":"https://www.utoledo.edu/offices/treasurer/tuition/graduate/","university of toledo|||bachelor of science in cybersecurity":"https://www.utoledo.edu/admission/international/tuition/","university of tulsa|||cybersecurity b.s.":"https://utulsa.edu/tuition-aid/tuition-costs/cost-undergraduate/","the university of utah|||master of science in cybersecurity management":"https://financialaid.utah.edu/tuition-and-fees/cost-of-attendance-graduate-general.php","university of wisconsinstout|||b.s. cybersecurity":"https://www.uwstout.edu/admissions-aid/paying-college/tuition-fees-payments","utah valley university|||bs in cybersecurity":"https://www.uvu.edu/tuition/docs/tuitionandfees2025-2026.pdf","wichita state university|||bs in cybersecurity":"https://www.wichita.edu/services/tuitionfees/index.php","worcester polytechnic institute|||master's in cyber security":"https://drive.google.com/file/d/1RLYuu-D3bJPic49amCp0AYCOLKv-yI6U/view?usp=drive_link","wright state university|||master of science in cyber security":"https://www.wright.edu/admissions/international/undergraduate-tuition-and-fees","wright state university|||bachelor of science in information technology and cybersecurity":"https://www.wright.edu/admissions/international/undergraduate-tuition-and-fees","yeshiva university|||m.s. in cybersecurity":"https://www.yu.edu/osf/tuition-fees/graduate","university of illinois springfield|||masters in cybersecurity management":"https://www.uis.edu/registrar/tuition-fees/spring-2026-tuition","purdue university|||cybersecurity, bs":"https://www.purdue.edu/treasurer/finance/bursar-office/tuition/fee-rates-2024-2025/undergraduate-tuition-and-fees-2024-2025/","virginia polytechnic institute and state university|||bachelor of science in computer engineering networking & cybersecurity major":"https://finaid.vt.edu/content/dam/finaid_vt_edu/Cost_of_Attendance/2627/UGNRON.pdf","alliant international university-san diego|||certificate in cybersecurity":"https://www.alliant.edu/admissions/tuition-and-fees","anderson university|||master of science in cybersecurity management":"https://andersonuniversity.edu/admission/tuition-and-fees/","university of florida|||bachelor of science in computer engineering specialization cyber security":"https://www.sfa.ufl.edu/cost/","university of southern california|||master of science in cybersecurity":"https://arr.usc.edu/tuition-and-fees/","carnegie mellon university|||master of science in information security":"https://www.cmu.edu/sfs/tuition/graduate/cit.html","johns hopkins university|||cybersecurity master's program":"https://ep.jhu.edu/admissions-aid/tuition-fees/","duke university|||cybersecurity master of engineering":"https://prattprofessional.bulletins.duke.edu/policies/tuition","tufts university|||ms in cybersecurity and public policy":"https://asegrad.tufts.edu/tuition-aid/school-engineering-soe","washington university in st. louis|||master of cybersecurity management":"https://engineering.washu.edu/academics/graduate-admissions/tuition-financial-assistance/index.html","washington university in st. louis|||ms in cybersecurity engineering":"https://engineering.washu.edu/academics/graduate-admissions/tuition-financial-assistance/index.html","washington university in st. louis|||graduate certificate in cybersecurity engineering":"https://drive.google.com/file/d/10JGWIaOzbsrckLvYq4LKiqHy4_Ri8Rt-/view?usp=sharing","north carolina state university|||computer science (bs): cybersecurity concentration":"https://studentservices.ncsu.edu/finances/estimated-cost-of-attendance/graduate-student-estimated-cost-of-attendance/","north carolina state university|||master of science in cybersecurity":"https://studentservices.ncsu.edu/finances/estimated-cost-of-attendance/graduate-student-estimated-cost-of-attendance/","indiana university bloomington|||m.s. in cybersecurity risk management":"https://studentcentral.indiana.edu/cost-of-iu/index.html","indiana university bloomington|||master's of science in secure computing":"https://studentcentral.indiana.edu/cost-of-iu/index.html","indiana university bloomington|||graduate certificate in cybersecurity":"https://studentcentral.indiana.edu/cost-of-iu/index.html","university of nebraska-lincoln|||space, cyber, and national security law, llm":"https://law.unl.edu/llm-program/","university of georgia|||master of science in cybersecurity and privacy":"https://osfa.uga.edu/costs/","george washington university|||master of science in cybersecurity in computer science":"https://graduate.engineering.gwu.edu/tuition-and-fees","george mason university|||cyber security engineering, ms":"https://studentaccounts.gmu.edu/wp-content/uploads/AY25-26_Tuition_and_Fee_Rates_Per_Credit.pdf","university at buffalo, state university of new york|||engineering science (cybersecurity) ms":"https://drive.google.com/file/d/1dST3jAghOlJByimTm_8C0IUhXXsA2x2b/view?usp=sharing","university at buffalo, state university of new york|||advanced certificate in cybersecurity":"https://drive.google.com/file/d/1dST3jAghOlJByimTm_8C0IUhXXsA2x2b/view?usp=sharing","florida state university|||cybersecurity major in ms in computer science program":"https://tuition.fsu.edu/tuition-and-fees","university of oregon|||cybersecurity undergraduate degree: bs":"https://financialaid.uoregon.edu/cost_of_attendance#resident-table","georgia state university|||computer science, m.s. security & privacy concentration":"https://admissions.gsu.edu/tuition/#grad-tuition","georgia state university|||information systems, m.s. concentrations cybersecurity":"https://admissions.gsu.edu/tuition/#grad-tuition","the university of kansas|||bachelor of science in cybersecurity engineering":"https://world.ku.edu/costs","san diego state university|||master of science in cybersecurity management":"https://sacd.sdsu.edu/financial-aid/financial-aid/eligibility/cost-of-attendance/cost-of-attendance-tables/graduate-and-doctoral-students","drexel university|||bachelors cyber security & information technology undergraduate degree":"https://drive.google.com/file/d/18eZQqpRwmRXmItBEYCQEXNEBoHbwrQ1V/view?usp=sharing","drexel university|||graduate certificate in computer security and privacy":"https://drive.google.com/file/d/1gER0ekI5AEE6M2Ui-dRfJMRhO0GiEHg3/view?usp=sharing","drexel university|||ms in cybersecurity":"https://drive.google.com/file/d/1gER0ekI5AEE6M2Ui-dRfJMRhO0GiEHg3/view?usp=sharing","the university of alabama|||cyber security, bs":"https://studentaccounts.ua.edu/tuition-rates/","west virginia university|||cybersecurity, b.s.":"https://tuition.wvu.edu/","university of arkansas|||computer science b.s. with cybersecurity concentration":"https://finaid.uark.edu/cost-of-attendance.php","university of nevada, reno|||online master of science in cybersecurity":"https://drive.google.com/file/d/1bc3EuFGGTIHzB-CHmj2HolfRDh5__Fqw/view?usp=sharing","loyola university chicago|||cybersecurity (bs)":"https://www.luc.edu/bursar/tuitionfees/summer2025tuitionfees/undergraduateschoolssummer2025/","depaul university|||bachelor of science cybersecurity":"https://www.depaul.edu/tuition-and-aid/undergraduate-tuition-and-fees","university of nevada, las vegas|||masters degree in cybersecurity":"https://www.unlv.edu/admissions/paying-for-college/costs","stevens institute of technology|||cybersecurity master's program":"https://www.stevens.edu/office-of-student-accounts/tuition-and-fees#2025-2026-undergraduate-tuition-and-fees","tulane university|||cyber technology, master of science":"https://studentaccounts.tulane.edu/sites/default/files/2023-06/sopa_grad_rate_2023-2024_v2.pdf","tulane university|||cybersecurity management, master of science":"https://studentaccounts.tulane.edu/sites/default/files/2023-06/sopa_grad_rate_2023-2024_v2.pdf","ohio university|||cybersecurity operations, b.s.":"https://www.ohio.edu/admissions/tuition","university of north carolina wilmington|||cybersecurity, b.s.":"https://uncw.edu/seahawk-life/money-matters/financial-aid/affording-your-education/cost-of-attendance","university of texas rio grande valley|||bachelor of science in cyber security":"https://www.utrgv.edu/ucentral/paying-for-college/cost-of-attendance/index.htm","abilene christian university|||certificate in cybersecurity":"https://acu.edu/admissions-aid/online/tuition-fees/","abilene christian university|||online bachelor of science in cybersecurity":"https://acu.edu/admissions-aid/online/tuition-fees/","fiji national university [nasinhu]|||postgraduate diploma in cyber security":"https://www.fnu.ac.fj/wp-content/uploads/2024/11/Tuition-Fees-Prospectus-2025.pdf","the university of the south pacific|||postgraduate diploma in cyber security":"https://www.usp.ac.fj/handbookandcalendar2026/2026-fees-schedule/international-student-tuition-fees-2026/","the university of the south pacific|||bachelor of networks & security":"https://www.usp.ac.fj/handbookandcalendar2026/2026-fees-schedule/international-student-tuition-fees-2026/","majan university college|||bsc (hons) data science (cybersecurity pathway)":"https://drive.google.com/file/d/1X_Dv0H8yzNEeLtzsQlcqqfxyQCs0o6Zq/view?usp=sharing","prince sultan university|||m.s in cybersecurity":"https://www.psu.edu.sa/en/admissions-Tuition-Fees","alfaisal university|||bachelor of cybersecurity":"https://admissions.alfaisal.edu/en/tution-fees","king fahd university of petroleum and minerals|||master of cybersecurity":"https://drive.google.com/file/d/102zDsSB01k9cQjEQJJlrrQQkoHui4vya/view?usp=drive_link","king khalid university|||bachelor in cyber security":"https://istudents.kku.edu.sa/en/Admission-Requirements-and-Procedures-for-International-Students","middle east technical university|||cybersecurity m.s.":"https://international.ncc.metu.edu.tr/en/tuition-scholarships","ecole polytechnique federale de lausanne|||cyber security - masters":"https://www.epfl.ch/education/studies/en/rules-and-procedures/study-taxes/tuition-fee-other-fees/","eth zurich|||master cyber security":"https://ethz.ch/content/dam/ethz/main/education/finanzielles/files-en/tuition-fees.pdf","kth royal institute of technology|||msc cybersecurity":"https://www.kth.se/en/studies/master/cybersecurity/fees-and-scholarships-for-cybersecurity-1.1076014","chalmers university of technology|||computer systems and cybersecurity, msc":"https://www.chalmers.se/en/education/application-and-admission/tuition-fees/","ben-gurion university of the negev|||master's degree in cyber space security":"https://in.bgu.ac.il/en/akis/Pages/Tuition-and-Expenses.aspx","university of jyvaskyla|||master's degree programme in cyber security":"https://www.jyu.fi/en/study-with-us/tuition-fees-and-other-financial-matters","ku leuven|||master of cybersecurity":"https://drive.google.com/file/d/1XYuwQheWVwAsIh-yJBs0MgpYSvIxdFqH/view?usp=sharing","universite libre de bruxelles|||master in cybersecurity with focus cryptalalysis and forensics":"https://drive.google.com/file/d/1yIMPsz_Bs9sJ0o6cFy5QP1w_nRWIzFrt/view?usp=sharing","singapore polytechnic|||diploma in cybersecurity & digital forensics":"https://www.sp.edu.sg/admissions/course-fees/full-time-diploma","eindhoven university of technology|||master's track cybersecurity":"https://www.tue.nl/en/education/become-a-tue-student/tuition-fees-and-other-study-costs/tuition-fee","abu dhabi university abu dhabi|||master of science in cybersecurity":"https://cdn.adu.ac.ae/images-container/docs/default-source/admissions-financials/all-tuition-fees-english.pdf?sfvrsn=d375c643_22","abu dhabi university abu dhabi|||master of law in cyberlaw and artificial intelligence":"https://cdn.adu.ac.ae/images-container/docs/default-source/admissions-financials/all-tuition-fees-english.pdf?sfvrsn=d375c643_22","ajman university|||bachelor of science in cybersecurity":"https://www.ajman.ac.ae/upload/files/financial_documents/2025-26/booklets/For_the_Academic_year_2025-2026_V03.pdf","technical university of denmark|||master of cyber security":"https://www.dtu.dk/english/education/graduate/fees-and-funding","furtwangen university of applied sciences|||bachelor of science cyber security":"https://www.hs-furtwangen.de/en/study/international/international-degree-seeking-students","karlsruhe institute of technology|||it security":"https://www.intl.kit.edu/istudies/3363.php","university of bonn|||master cyber security (msc)":"https://www.uni-bonn.de/en/studying/application-admission-and-enrollment/costs","hochschule albstadt-sigmaringen|||master's program advanced it security (m.sc.)":"https://www.hs-albsig.de/studienangebot/masterstudiengaenge/life-science-innovation/requirements-and-admission/","hochschule albstadt-sigmaringen|||digital forensics | online distance learning (m.sc.)":"https://www.hs-albsig.de/fileadmin/user_upload/hsas/01_studienangebot/master/df/downloads/dokumente/Gebuehrenuebersicht_DF_ab_SS25.pdf","rheinische friedrich-wilhelms-universitat bonn|||cybersecurity (b. sc.)":"https://www.uni-bonn.de/en/studying/application-admission-and-enrollment/applications-from-international-students","hochschule albstadt-sigmaringen|||it security studies (b.sc.)":"https://www.hs-albsig.de/studienangebot/masterstudiengaenge/life-science-innovation/requirements-and-admission/","technische hochschule wurzburg-schweinfurt|||bachelor's degree programme information security (b.sc.)":"https://www.swerk-wue.de/en/about-us/semesterbeitrag-wofuer-eigentlich","zhejiang university|||masters in cyberspace security":"https://zju.cucas.cn/program/Cyberspace-Security-57366.html","khon kaen university|||bachelors degree cybersecurity":"https://www.en.kku.ac.th/web/en/tuition-feesliving-expenses/","dublin business school|||master of science (msc.) in cybersecurity":"https://www.dbs.ie/docs/default-source/fee-sheets/dbs-fees-international.pdf","southeast technological university|||master of science cybersecurity, privacy and trust":"https://www.setu.ie/current-students/fees-and-grants/fees/global-fees","universidad nacional de colombia|||cybersecurity essentials":"https://catc.unal.edu.co/academias/costos","esiia|||bts cybersecurity":"https://esiia.fr/tarifs-et-financements/","esiia|||bachelor's degree in network and cybersecurity administration":"https://esiia.fr/tarifs-et-financements/","esiia|||specialized master's degree in cybersecurity":"https://esiia.fr/tarifs-et-financements/","universite de limoges|||master cryptis - information security computer science":"https://ressources.campusfrance.org/pratique/etablissements/en/univ_limoges_en.pdf","esiea paris|||bachelor's degree in cybersecurity (cti equivalent, bac+3)":"https://www.esiea.fr/admissions-bachelor-cybersecurite-cti/","universite de montpellier (um)|||diploma in cybercrime: law, information security & digital forensics":"https://cybercrime.edu.umontpellier.fr/inscriptions-pedag/","ece - paris|||cybersecurity major":"https://www.ece.fr/en/rates-and-financing/","isen west nantes|||cybersecurity engineering":"https://isen-ouest.fr/en/international/studying-at-isen-ouest/international-applicants/","isen west caen|||cybersecurity engineering":"https://isen-ouest.fr/en/international/studying-at-isen-ouest/international-applicants/","isen west brest|||cybersecurity engineering":"https://isen-ouest.fr/en/international/studying-at-isen-ouest/international-applicants/","isen mediterranee|||bachelor in cybersecurity":"https://isen-mediterranee.fr/en/admissions-frais-dinscription/","epita paris|||bachelors degree in cybersecurity":"https://dossier.parcoursup.fr/Candidats/public/fiches/afficherFicheFormation?g_ta_cod=51316&typeBac=0&originePc=0","efrei paris (universite paris-pantheon-assas)|||bachelor's degree in cybersecurity & ethical hacking":"https://eng.efrei.fr/international-admission/tuition-fees-and-financial-assistance/","universite de pau et du pays de l'adour|||but networks and telecommunications cybersecurity training program":"https://formation.univ-pau.fr/fr/inscription/droits-d-inscription.html","universite de rennes|||master's degree in cybersecurity, specializing in software and hardware security":"https://master-greensuscat.univ-rennes.fr/admission-and-tuition-fees","paris american international university|||bachelor in cyber security":"https://paiu.fr/tuition-fees-payment-test/","paris american international university|||master in cyber security":"https://paiu.fr/tuition-fees-payment-test/","carleton university|||bachelor of cybersecurity":"https://carleton.ca/studentaccounts/tuition-fees/fw-ug/f25w26-ug-international/","mcgill university|||graduate certificate in cybersecurity":"https://drive.google.com/file/d/1yMJmf8kaXUchrjAK0V-Oa33MdhOZZEdD/view?usp=sharing","saskatchewan polytechnic|||cyber security pgc":"https://saskpolytech.ca/programs-and-courses/international/documents/international-estimated-tuition-and-fees.pdf","southern alberta institute of technology|||bachelor of technology  cyber security":"https://www.sait.ca/programs-and-courses/degrees/bachelor-of-technology-cyber-security#costs","thompson rivers university|||computer network and cybersecurity diploma":"https://www.tru.ca/truworld/future-students/fees.html","university of guelph|||master of cybersecurity and threat intelligence (mcti)":"https://uoguelphca-my.sharepoint.com/:x:/g/personal/sfscomm_uoguelph_ca/EWOnOW6eFNhLn3KAjltodt4Bew0n7rlFfF4k45vcJJRRQw?e=JN3mAs&activeCell=%272025%27!A1&action=embedview","university of guelph|||master of cybersecurity leadership and cyberpreneurship":"https://uoguelphca-my.sharepoint.com/:x:/g/personal/sfscomm_uoguelph_ca/EWOnOW6eFNhLn3KAjltodt4Bew0n7rlFfF4k45vcJJRRQw?e=JN3mAs&activeCell=%272025%27!A1&action=embedview","university of new brunswick|||master of applied cybersecurity":"https://www.unb.ca/finance/_assets/documents/financial-services/fredericton-tuition/grad-summer/all-other/fred_gr_cybersecurity_sm.pdf","wrexham university|||bsc (hons) cyber security":"https://wrexham.ac.uk/international-students/international-fees/","wrexham university|||msc cyber security":"https://wrexham.ac.uk/international-students/international-fees/","eotvos lorand university|||msc computer science (cybersecurity)":"https://apply.elte.hu/courses/course/313-msc-computer-science-msc-course---cybersecurity-specialization","obuda university|||cyber security engineering (msc)":"https://uni-obuda.hu/tuition-fees/","ludovika university of public service|||ma international cybersecurity studies":"https://en.uni-nke.hu/admissions/tuition-fees","university of porto|||masters in information security":"https://sigarra.up.pt/fcup/en/web_base.gera_pagina?p_pagina=propinas%20do%20mestrado%20em%20seguran%c3%a7a%20inform%c3%a1tica%c2%a02024-2025","national university of science and technology politehnica bucharest|||advanced cybersecurity":"https://www.international.upb.ro/assets/docs/academics/regulations/Non-EU_Tuition_Fees.pdf","bucharest university of economic studies|||it&c security master - cyber security master":"https://ism.ase.ro/admission/international-students-admission/","university of doha for science and technology|||master of science in artificial intelligence and cognitive cybersecurity (m.sc. aicc)":"https://www.udst.edu.qa/admissions/admissions-information/tuition-and-fees","university of doha for science and technology|||bachelor of science in data and cyber security (b.sc. dcs)":"https://www.udst.edu.qa/admissions/admissions-information/tuition-and-fees","community college of qatar|||bachelor of science in cybersecurity":"https://www.community.edu.qa/English/Admissions/Pages/Fees-and-Charges.aspx","international college of management|||master of information technology (cyber security)":"https://drive.google.com/file/d/1-IdmpiCY5O2LFCJMn_ye_qvHP5OEvXCR/view?usp=sharing","melbourne institute of higher education|||bachelor of information technology (cyber security)":"https://www.mihe.vic.edu.au/wp-content/uploads/2024/12/MIHE-BIT-Cyber-security-Flyer.pdf","melbourne institute of higher education|||master of information technology (cyber security)":"https://www.mihe.vic.edu.au/wp-content/uploads/2024/12/MIHE-MIT-Cyber-security-Flyer.pdf","university in new south wales|||masters in cyber security":"https://studyonline.unsw.edu.au/fees","australian academy in higher education|||masters in cyber security":"https://aahe.edu.au/fees/","australian academy in higher education|||graduate certificate in cyber security management":"https://aahe.edu.au/fees/","australian academy in higher education|||graduate certificate in cyber security systems":"https://aahe.edu.au/fees/","australian academy in higher education|||graduate diploma in cyber security":"https://aahe.edu.au/fees/","torrens university australia|||master of cybersecurity":"https://cdn.intelligencebank.com/au/share/RyzZ/D1G8V/jlMdo/original/2026-International-Fee-Schedule","torrens university australia|||graduate certificate of cybersecurity":"https://cdn.intelligencebank.com/au/share/RyzZ/D1G8V/jlMdo/original/2026-International-Fee-Schedule","ural federal university|||information security":"https://urfu.ru/index.php?id=81","ural federal university|||computer systems security":"https://urfu.ru/en/international/programs-and-courses/bachelors-degree-programs-in-russian/","california state university, fullerton|||computer science, cybersecurity concentration, b.s.":"https://sbs.fullerton.edu/students/all-student-fees/","depaul university|||master of science cybersecurity":"https://www.depaul.edu/tuition-and-aid/graduate-and-professional-tuition-and-fees","vignan's foundation for science,technology & research|||b.tech in cyber security":"https://vignan.ac.in/newvignan/fee_str.php","asha m. tarsadia institute of computer science and technology|||b.tech. cse (cyber security)":"https://drive.google.com/file/d/1Rf78n0mmqbbyraQXV8LXNzf9fyhg73h4/view?usp=sharing","woxsen university|||b.tech (blockchain, iot & cybersecurity)":"https://woxsen.edu.in/fsd/btechcsedataiotfee.pdf","woxsen university|||bca specialization: cybersecurity":"https://woxsen.edu.in/fsd/bcafee.pdf","yenepoya university|||b.sc cybersecurity, ethical hacking and data analytics":"https://www.yenepoya.edu.in/img/pdf/YEN%20MANGALORE%202024%20-%202025%20FEES%20STRUCTURE%20(2)%201.pdf","yenepoya university|||msc cyber security and ethical hacking":"https://www.yenepoya.edu.in/img/pdf/YEN%20MANGALORE%202024%20-%202025%20FEES%20STRUCTURE%20(2)%201.pdf","pondicherry university|||m.tech. network & information security":"https://www.pondiuni.edu.in/wp-content/uploads/2025/01/PGInformationBrochureas2025-21.01.2025.pdf","reva university|||m.tech in cyber security":"https://drive.google.com/file/d/1fmepJ31Dfjm_qh5g_wunPXVkMUXKCSpc/view?usp=drive_link","reva university|||bachelor of science in computer science with specialization in cyber security":"https://drive.google.com/file/d/1fmepJ31Dfjm_qh5g_wunPXVkMUXKCSpc/view?usp=drive_link","reva university|||bca - cyber security & digital forensics":"https://drive.google.com/file/d/1fmepJ31Dfjm_qh5g_wunPXVkMUXKCSpc/view?usp=drive_link","a.k.s. university|||b.tech cse cyber security":"https://www.aksuniversity.ac.in/latest-fee-structure","academy of maritime education and training|||b.tech in computer science and engineering (cyber security)":"https://www.ametuniv.ac.in/pdfs/mandatory-disclosure-2025-26.pdf","ajeenkya d.y. patil university|||b. tech in computer science & engineering (cyber forensics & information security)":"https://adypu.edu.in/wp-content/uploads/2024/07/20.ADYPU_Fees-Structure_24_25.pdf","ajeenkya d.y. patil university|||bachelor of technology in information technology (cloud technology and information security)":"https://adypu.edu.in/wp-content/uploads/2024/07/20.ADYPU_Fees-Structure_24_25.pdf","ajeenkya d.y. patil university|||mca information security":"https://adypu.edu.in/wp-content/uploads/2024/07/20.ADYPU_Fees-Structure_24_25.pdf","amrita vishwa vidyapeetham|||m. tech. in cyber security":"https://webfiles.amrita.edu/2022/05/M.Tech-fee-structure.pdf","c. v. raman global university|||b.tech computer science engineering.(iot & cyber security)":"https://cgu-odisha.ac.in/fee-structure/","career point university|||m.tech cyber security":"https://cpur.in/course-fee-detail","dayananda sagar university|||m.sc in cyber security":"https://www.dsu.edu.in/eligibility","dayananda sagar university|||b.sc in cyber security":"https://www.dsu.edu.in/eligibility","national law institute university bhopal|||b.sc. ll.b. (hons.) [cyber security]":"https://nliu.ac.in/fee-structure/","g.h. raisoni college of engineering and management pune (savitribhai phule pune university)|||btech in cse in cyber security":"https://rgicdn.s3.ap-south-1.amazonaws.com/ghrcempune/pdf/circular-fra-fee.pdf","gna university|||b. tech - computer science & engineering with cyber security":"https://www.gnauniversity.edu.in/fee-structure","guru jambeshwar university of science and technology|||bachelor of science (hons. / hons. with research) - master of science in computer science (cyber security)":"https://gjust.ac.in/portal/upload/Fee%20Structure%202025-26_07May2025_14-46-24-05.pdf","indraprastha institute of information technology delhi|||master of science(information security)":"https://iiitd.ac.in/academics/mtech","indrashil university|||post graduate diploma in cyber security and digital forensic in collaboration with ec-council":"https://indrashiluniversity.edu.in/fees-structure","indus university|||b.tech in cyber security":"https://indusuni.ac.in/ug-admissions/","international institute of information technology hyderabad|||m.tech in computer science and information security":"https://pgadmissions.iiit.ac.in/fee/","itm university gwailor|||b.tech -cyber":"https://www.itmuniversity.ac.in/admission/fee-structure","indian institute of information technology, una|||b.tech computer science and engineering (cybersecurity)":"https://cdn.iiitu.ac.in/uploads/news/fees_structure_iiituna.pdf","indian institute of information technology, una|||m.tech cse with specialization in data science/cyber security":"https://cdn.iiitu.ac.in/uploads/admission/M.%20Tech.%20Fee%20Structure%20Batch%202025-26.pdf","indian institute of information technology, design and manufacturing, kurnool|||m.tech in computer science and engineering with specialization in cyber security":"https://files.iiitk.ac.in/uploads/academics/feestructure/M.Tech_FeeStructure_AY2025_26.pdf","central university of punjab, bathinda|||m. tech computer science & engineering  (cyber security)":"https://cup.edu.in/sites/default/files/International_Students_Div/Fee_Structure-PG-2024-25.pdf","sardar patel university of police, security and criminal justice jodhpur|||m.tech cyber security":"https://www.policeuniversity.ac.in/univ_uploads/syllabus/Various%20Course%20Fee%20Structure.pdf","indian institute of information technology bhopal|||b. tech cse  cyber security":"https://iiitbhopal.ac.in/Document/Admission/B.Tech%20FEE%20STRUCTURE%202022-23.pdf","netaji subhas university of technology|||b.tech.- information technology (network & information security)":"https://drive.google.com/file/d/1uayccnPvMdwBCu_qrWvWpmAnmXQcodj3/view?usp=drive_link","jiet jodhpur|||b.tech in cyber security":"https://www.jietjodhpur.ac.in/fees-structure","jaipur national university|||bca cyber security":"https://www.jnujaipur.ac.in/programmes/ug-programmes","jaipur national university|||b. tech cse  cyber security":"https://www.jnujaipur.ac.in/programmes/ug-programmes","jamia hamdard|||m.tech. (cse) with specialization in cyber forensics & information security":"https://ums.jamiahamdard.ac.in/Files/Fee_structure.pdf","jawaharlal nehru technological university hyderabad|||m.tech - cyber forensic & information security / cyber security":"https://jntuhceh.ac.in/uploads/M.Tech_PTPG_I_year_IISem_and_II_year_II_Sem_2023_and_2024_batch_fee_notification.pdf","jeppiaar university|||b. tech computer science and engineering (cyber security)":"https://jeppiaaruniversity.ac.in/annual-fees-details/","jharkhand rai university|||bca  cloud technology information security":"https://drive.google.com/file/d/1maFK_ebpeROASQyTjJdms8lFj_R9z9c3/view?usp=drive_link","jspm university|||master of science (cyber security)":"https://jspmuni.ac.in/post-graduate-pg","kk modi university|||b.tech cse in cyber security & digital forensics":"https://kkmu.edu.in/admissions/domestic-saarc-students/","kalasalingam academy of research and education|||b.tech.- computer science and engineering (cybersecurity)":"https://www.kalasalingam.ac.in/fee-details/","karpagam academy of higher education|||b.e. computer science and engineering (cyber security)":"https://kahedu.edu.in/n/wp-content/uploads/2019/11/fees_final_2017-18.pdf","kle technological university|||bca honours with cyber security specialization":"https://www.kletech.ac.in/belagavi/admissions/fee-structure","madhya pradesh bhoj (open) university|||post graduation diploma in cyber security":"https://drive.google.com/file/d/1B8gs45E4NZkJxic3wsWxv5_RRovaLa6f/view?usp=sharing","university of madras|||m. sc. cyber forensics and information security":"https://www.unom.ac.in/webportal/uploads/admissions/fees_structure_2024.pdf","maharishi university of information technology|||b.tech cse with cyber security":"https://noida.maharishiuniversity.ac.in/upload/Image/24a4b27a-4e23-4a63-ac7d-ff30e6120892_Noida%20All%20Course%20Brochure%20with%20Fee.pdf","manipal academy of higher education|||m. tech in computer science and engineering (cyber security)":"https://www.manipal.edu/content/dam/manipal/mu/documents/Admissions/adm2025/FEES%20UPDATION%20-%20GENERAL.pdf","mody university of science & technology|||b.tech (computer science and engineering-cyber security)":"https://www.modyuniversity.ac.in/fee-structure-set/","niit university|||b.tech cyber security":"https://niituniversity.in/admissions/fee-structure","nitte|||mtech cyber security":"https://nitte.edu.in/fee/PGGEN.pdf","noida international university|||b.tech cse cybersecurity in collaboration with ibm":"https://niu.edu.in/courses-fee-structure-for-2025-26/","noorul islam centre for higher education|||bsc cyber forensics":"https://www.niuniv.com/courses-fees.php","sr university|||m.tech. computer science and engineering (cyber security)":"https://sru.edu.in/fee-scholarship","scope global skills university|||msc (cyber security)":"https://sgsuniversity.ac.in/wp-content/uploads/2025/05/Prospectus-with-fee-structure.pdf","kj somaiya school of engineering (somaiya vidyavihar university)|||master of technology information technology (information security)":"https://kjsce.somaiya.edu/en/admission/mtech/","kansas state university|||b.s. in cybersecurity":"https://drive.google.com/file/d/1Y1XTNvwwotlPysOVYgVlq_45Cd-GPd_9/view?usp=sharing","bow valley college|||cybersecurity - post-diploma certificate":"https://drive.google.com/file/d/1qdwetwefKX-EPNKmF4tgiwRO8aiSwu39/view?usp=sharing","anand vishwa gurukul college of law|||post graduate diploma in cyber law and information technology":"https://lawcollege.anandvishwagurukul.com/wp-content/uploads/2025/07/4.34-PG-Diploma-Cyber-Law-IT.pdf","open university|||postgraduate diploma in cyber security":"https://drive.google.com/file/d/1dr2FTMrPzDcRBiuNZp-6q9Opo8poVlEc/view?usp=drive_link","kannur university|||post graduate diploma in cyber security":"https://drive.google.com/file/d/1ifOTRLV59O5mMZaRSyHZjXnp6YR1dFFn/view?usp=sharing","sunrise university|||the diploma in cyber security":"https://drive.google.com/file/d/1eLKgIifsoRnP6sH1qmscIa5L4xDSfoEf/view?usp=sharing","the university of kansas|||cybersecurity  graduate certificate":"https://drive.google.com/file/d/1xtu4zypcdZNeD5XCcibs7viTCO-0makc/view?usp=sharing","ohio state university|||cybersecurity offense and defense graduate certificate":"https://drive.google.com/file/d/1xFhajqtfm4bnrfRn4rwcXVuZS7pY7MXZ/view?usp=sharing","abco technology|||cyber security professional":"https://abcotechnology.edu/tuition-rates-fees/","dr. d.y.patil arts, commerce & science college|||b.sc (cyber and digital science)":"https://acs.dypvp.edu.in/DownloadS3File.aspx?file=UG-fee-structure-26-27","lokmanya tilak college of engineering|||b.tech. computer science and engineering (iot and cyber security including blockchain technology)":"https://ltce.in/assets/Fee_Structure_AY_2025_26.pdf","ac patil college of engineering|||b.tech. cse (internet of things and cyber security including block chain technology)":"https://acpce.ac.in/wp-content/uploads/2025/08/FE.pdf","graphic era university|||bca hons in cyber security":"https://geu.ac.in/fee/bca-cybersecurity","kalasalingam academy of research & education|||b.tech. computer science and engineering (cybersecurity)":"https://www.kalasalingam.ac.in/fee-details/","virginia commonwealth university|||computer science bachelor of science with a concentration in cybersecurity":"https://admissions.vcu.edu/cost-aid/tuition-fees/","sushant university|||b.tech.- computer science and engineering in cyber security":"https://sushantuniversity.edu.in/admin-assets/uploaddata/Fees2024.pdf","takshashila university|||b. tech computer science & engineering (cyber security)":"https://drive.google.com/file/d/1xJP4FVUQPkzn7S9f4TjuSrYlQdEz5CcI/view?usp=drive_link","universal skilltech|||b.tech. cyber security":"https://www.universalskilltechuniversity.edu.in/admissions","cvm university|||bachelor of technology (cyber security)":"https://drive.google.com/file/d/1EcCwqd_IHiP1B_wAm2x6Kr2kLwQGvcEy/view?usp=drive_link","quantum university|||b.tech. cse (hons) cyber security and digital forensic":"https://quantumuniversity.edu.in/downloads/Fee_Structure/Quantum_School_of_Technology.pdf","sagar institute of research & technology|||b.tech. computer science and engineering (cyber security)":"https://www.sirtbhopal.ac.in/blogs/btech-cse-course-details-full-form-admission-fees-syllabus-specialization-top-colleges-career-options","indian institute of technology kanpur|||bachelor of cybersecurity (b.cyber.)":"https://www.iitk.ac.in/dosa/data/Fee-Structure-for-New-UG-for-2026-2027-1st-07-07-26.pdf","kes b k shroff college of arts & m h shroff college of commerce|||b.tech. computer science and engineering (cyber security)":"https://kessc.edu.in/document/course-wise-fees-structure/","bk birla college of arts and science kalyan|||b.voc. cyber security & forensics":"https://bkbck.edu.in/wp-content/uploads/2026/06/Fees-Structure.pdf","florida polytechnic university|||bachelor of science in cybersecurity engineering":"https://floridapoly.edu/admissions/undergraduate-tuition/","sam houston state university|||cybersecurity, bachelor of science":"https://www.shsu.edu/cost-aid/cost-attendance","anderson university|||bachelor of science (bs), cybersecurity":"https://drive.google.com/file/d/1ammvDDx9cjsmUX-87-QddNXnR7_0U6nz/view?usp=sharing","al ain university abu dhabi|||bachelor of science in cybersecurity":"https://aau.ac.ae/en/admission/financial-info/financial-information","abu dhabi university al ain|||bachelor of science in cybersecurity engineering":"https://www.adu.ac.ae/admissions/admission-in-adu/international-students/financials/undergraduate-fees-for-international-students","ozford institute of higher education|||bachelor of cyber security":"https://ozford.edu.au/admissions/fees/","rajiv gandhi national institute of youth development|||m.sc. computer science (cyber security)":"https://rgniyd.gov.in/content/fee-structure-student-india-0","institute of advanced research|||m.sc. in digital forensics and cyber security":"https://iar.ac.in/admissions/fees-scholarships/","srm university, amaravathi|||m.tech. cyber security":"https://www.srmap.edu.in/admission/seas-mtech-tuition-fee/","vellore institute of technology banglore|||m.sc. cybersecurity":"https://vitbangalore.in/fees-important-dates/","niit university|||m.tech (cyber security) with infosys ltd.":"https://niituniversity.in/admissions/fee-structure","florida international university|||ms computer engineering: security":"https://drive.google.com/file/d/1PoKt0QLyl4r2gpmILs9nKN4oqwtL3bPb/view?usp=sharing","university of the pacific|||master of science in cybersecurity":"https://www.pacific.edu/engineering/academics/online-masters-cybersecurity/tuition-and-fees","concordia university of edmonton|||master of information system security management":"https://concordia.ab.ca/wp-content/uploads/2026/04/2026-27-New-International-Master-of-ISSM-ISAM-INTERNATIONAL-Students.pdf?x37295","university of granada|||master of international cybersecurity and cyberintelligence":"https://apply.arqus-alliance.eu/courses/course/11-micac-master-international-cybersecurity-and-cyberintelligence","kharkiv national university of radio electronics|||master of science in cyber security (administrative management in the field of information security)":"https://nure.ua/en/applicants/admission-for-foreign-citizens/specialties-educational-programs-duration-and-cost-of-study-for-foreign-citizens","tilburg university|||artificial intelligence and cybersecurity":"https://www.tilburguniversity.edu/students/administration/tuition-fees","alma mater studiorum - universita di bologna|||master in cybersecurity: from design to operations":"https://www.unibo.it/en/study/phd-professional-masters-specialisation-schools-and-other-programmes/professional-master/2025-2026/cybersecurity-from-design-to-operations-1","bar-ilan university|||imba and cyber security":"https://imba.biu.ac.il/tuition","koc university|||masters in cyber security":"https://international.ku.edu.tr/graduate-programs/tuition-and-scholarships/","university of north carolina at charlotte|||cybersecurity, m.s.":"https://isso.charlotte.edu/wp-content/uploads/sites/1179/2026/06/2026-2027-UNCC-Estimated-Cost-of-Attendance-Graduate-1-20.pdf","university of buraimi|||master of science in cybersecurity":"https://drive.google.com/file/d/18SfJBjrPqUR5g6izP-NWPkPEUWNs-2Dg/view?usp=sharing","dakota state university|||cyber defense, m.s.":"https://dsu.edu/admissions/graduate/cost-aid/tuition-fees.html","shaheed sukhdev college of business studies|||post graduate diploma in cyber security and law":"https://sscbs.du.ac.in/wp-content/uploads/2025/09/fee-structure-PGDCSL-1.pdf","university of north carolina at charlotte|||information security and privacy, graduate certificate":"https://isso.charlotte.edu/wp-content/uploads/sites/1179/2026/06/2026-2027-UNCC-Estimated-Cost-of-Attendance-Graduate-1-20.pdf","eastern kentucky university|||graduate certificate  cybersecurity and digital forensics":"https://drive.google.com/file/d/1Y9F3uT5suoXc4Osdz9r-89_4s2aBJ0It/view?usp=sharing"};

/**
 * Look up fee page URL for a course.
 * Pass 1: Exact ASCII-normalised key match.
 * Pass 2: Strict word-overlap fuzzy match.
 *   - Generic words (university, institute, college, cyber, security ...) are
 *     excluded from scoring so they cannot create false positives.
 *   - Institute must share >= 1 specific (non-generic) word.
 *   - Course must share >= 3 specific words AND cover >= 50% of query words.
 * Returns URL or null. Never guesses when not confident.
 */
function getFeesLink(university, courseName) {
    if (!university || !courseName) return null;

    const norm = s => (s || '').toLowerCase()
        .normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();

    const instKey  = norm(university);
    const courseKey = norm(courseName);

    // Pass 1: exact composite key
    const exact = FEES_MAP[instKey + '|||' + courseKey];
    if (exact) return exact;

    // Words too generic to discriminate -- exclude from scoring
    const STOP = new Set([
        'university','institute','college','technology','engineering','science',
        'computer','cyber','security','information','network','management',
        'education','studies','school','academy','national','centre','center',
        'india','indian','advanced','research','applied','system','systems',
        'with','from','that','this','have','been','will','their',
        'btech','mtech','bsca','bca','mca','msc','bsc','phd',
        'hons','tech','prog','programme','program','specialization',
        'specialisation','including','block','chain','internet','things',
    ]);

    const sigWords = str => str.split(/\s+/).filter(w => w.length >= 4 && !STOP.has(w));

    const instSig  = sigWords(instKey);
    const courseSig = sigWords(courseKey);

    // If university has no specific/unique words we cannot safely match
    if (instSig.length === 0) return null;

    let bestLink  = null;
    let bestScore = -1;

    for (const key of Object.keys(FEES_MAP)) {
        const sep = key.indexOf('|||');
        if (sep === -1) continue;
        const ki = key.slice(0, sep);
        const kc = key.slice(sep + 3);

        // Institute: >= 1 specific word must match
        const kiSig = new Set(sigWords(ki));
        const instMatch = instSig.filter(w => kiSig.has(w)).length;
        if (instMatch < 1) continue;

        // Course: >= 3 specific words AND >= 50% of query words matched
        const kcSig = new Set(sigWords(kc));
        const courseMatch = courseSig.filter(w => kcSig.has(w)).length;
        if (courseMatch < 3) continue;
        if (courseSig.length > 0 && courseMatch / courseSig.length < 0.5) continue;

        const score = instMatch * 10 + courseMatch;
        if (score > bestScore) { bestScore = score; bestLink = FEES_MAP[key]; }
    }

    return bestLink;
}

// ── State ─────────────────────────────────────────────────────────
let allCourses = [];           // All documents from MongoDB (loaded once)
let domainChart = null;
let statusChart = null;
let correctionsChart = null;

let vfPage = 1;                // Verification tab pagination
let cfPage = 1;                // All Courses tab pagination
const PAGE_SIZE = 100;

let vfFilter = { search: '', status: 'issues', country: 'all', domain: 'all', courseType: 'all' };
let cfFilter = { search: '', status: 'all', country: 'all', domain: 'all', qs: 'any', courseType: 'all' };

let modalCourse = null;        // Currently open course in modal

// ── Custom State ───────────────────────────────────────────────────
let sfPage = 1;
let sfFilter = { search: '', domain: 'all', courseType: 'all' };
let sortState = {
    vf: { col: 'id', dir: 1 },
    cf: { col: 'id', dir: 1 },
    sf: { col: 'solved_ts', dir: 1 }
};

function getOriginalStatus(c) {
    if (c.pdf_table && c.pdf_table.some(r => r.status && r.status.toUpperCase() === 'FALSE')) return 'Discrepancy';
    if (c.disc_reason && (c.disc_reason.includes('404') || c.disc_reason.toLowerCase().includes('website') || c.disc_reason.toLowerCase().includes('not found'))) return 'Error';
    if (c.disc_reason) return 'Discrepancy';
    return 'Verified';
}

function getOriginalCategory(c) {
    const s = getOriginalStatus(c);
    if (s === 'Error') return 'website_issue';
    if (s === 'Discrepancy') return 'mismatch';
    return 'verified';
}

function sortCourses(list, state) {
    return list.sort((a, b) => {
        let vA = a[state.col];
        let vB = b[state.col];
        
        if (state.col === 'solved_ts') {
            vA = a.solved_ts || 0;
            vB = b.solved_ts || 0;
            return (vB - vA) * state.dir;
        } else if (state.col === 'domain') {
            vA = getDomainLabel(a.id);
            vB = getDomainLabel(b.id);
        } else if (state.col === 'courseType') {
            vA = (a.domain || 'Uncategorised').toLowerCase();
            vB = (b.domain || 'Uncategorised').toLowerCase();
        } else if (state.col === 'name') {
            vA = (vA || '').toLowerCase();
            vB = (vB || '').toLowerCase();
        }
        
        if (typeof vA === 'string' && typeof vB === 'string') {
            return vA.localeCompare(vB) * state.dir;
        }
        if (vA < vB) return -1 * state.dir;
        if (vA > vB) return 1 * state.dir;
        return 0;
    });
}

// ── API Base URL (Cloudflare Worker) ─────────────────────────────
// The actual deployed Cloudflare Worker URL
const API_BASE_URL = 'https://course-verifier-api.shlokparekh08.workers.dev';

// ── API Fetchers (Cloudflare Worker) ─────────────────────────────

/**
 * Fetch ALL courses from the Cloudflare Worker API.
 * Returns full sorted array.
 */
async function fetchAllCourses() {
    setLoaderSub('Fetching courses from database…');
    const res = await fetch(`https://raw.githubusercontent.com/Shlok-Parekh09/course-verifier/main/frontend/infinityfree/data/courses.json`);
    if (!res.ok) {
        const err = await res.text();
        throw new Error(`API error ${res.status}: ${err}`);
    }
    const data = await res.json();
    
    let docs = [];
    let pending = [];
    
    // Parse the static courses.json from GitHub
    if (Array.isArray(data)) {
        docs = data;
    } else {
        docs = data.courses || data.documents || [];
    }

    // Now fetch the real-time solves from Cloudflare Worker
    try {
        const solvesRes = await fetch(`${API_BASE_URL}/api/solves.json?t=${Date.now()}`);
        if (solvesRes.ok) {
            const solvesData = await solvesRes.json();
            if (solvesData.pending_solves) pending = solvesData.pending_solves;
            if (solvesData.solved) {
                // Cloudflare might return object map { "123": {by:"..."} }
                const mapped = Object.entries(solvesData.solved).map(([id, val]) => ({
                    id: parseInt(id),
                    ...val
                }));
                pending = pending.concat(mapped);
            }

            let maxTs = 0;
            pending.forEach(s => {
                const ts = (s.update && s.update.solved_ts) ? s.update.solved_ts : (s.ts || 0);
                if (ts > maxTs) maxTs = ts;
            });
            if (maxTs > 0) {
                const dateObj = new Date(maxTs);
                const el = document.getElementById('last-updated-label');
                if (el) el.textContent = 'Last Updated: ' + dateObj.toLocaleString();
            }
        }
    } catch (e) {
        console.error("Failed to fetch initial solves", e);
    }

    // Merge server solves into localStorage (once, at page load).
    // Server is authoritative for solves other users did on other browsers.
    mergeCloudflaresolves(pending);

    // Apply all localStorage solves to the in-memory course list.
    // This covers both server-synced solves and local optimistic solves.
    applyLocalSolves(docs);

    // Normalize Course Types
    for (const c of docs) {
        if (c.domain) {
            let t = c.domain.toLowerCase().trim();
            if (t.includes("bachelor")) c.domain = "Bachelor's Degree";
            else if (t.includes("master")) c.domain = "Master's Degree";
            else if (t === 'diploma') c.domain = "Diploma";
            else if (t === 'post graduate diploma') c.domain = "Post Graduate Diploma";
            else if (t === 'post graduate certificate') c.domain = "Post Graduate Certificate";
            else if (t === 'certificate') c.domain = "Certificate";
            else if (t === 'free to audit') c.domain = "Free to Audit";
            else if (t === 'free') c.domain = "Free";
            else if (t === 'high value low cost') c.domain = "High Value Low Cost";
            else c.domain = c.domain.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
        }
    }

    setLoaderSub(`Loaded ${docs.length} courses…`);
    return docs;
}

/**
 * Write an updated course back to the Cloudflare Worker queue.
 */
// ─── User Identification ───────────────────────────────────────────
let currentUserId = localStorage.getItem('cv_user_id');
if (!currentUserId) {
    currentUserId = 'user_' + Math.random().toString(36).substring(2, 9);
    localStorage.setItem('cv_user_id', currentUserId);
}

// ─── Batched Solve Queue ─────────────────────────────────────────
// Instead of sending 1 request per solve, we queue them up and send
// them all at once every 10 seconds. If 100k users each do 10 solves
// quickly, this turns 1,000,000 requests into 100k requests max.
let pendingSolveQueue = [];
let isFlushingQueue = false;

async function flushSolveQueue() {
    if (pendingSolveQueue.length === 0 || isFlushingQueue) return;
    isFlushingQueue = true;
    
    // Grab everything currently in the queue
    const batch = [...pendingSolveQueue];
    pendingSolveQueue = []; // clear it immediately so new clicks start a new batch
    
    try {
        const res = await fetch(`${API_BASE_URL}/api/solve_course`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ solves: batch })
        });
        
        if (!res.ok) {
            console.error('Failed to flush solve queue', await res.text());
            // Put them back in the queue to try again later
            pendingSolveQueue = [...batch, ...pendingSolveQueue];
        }
    } catch (err) {
        console.error('Network error flushing solve queue', err);
        // Put them back in the queue to try again later
        pendingSolveQueue = [...batch, ...pendingSolveQueue];
    } finally {
        isFlushingQueue = false;
    }
}

// Flush the queue every 10 seconds automatically
setInterval(flushSolveQueue, 10000);
// Also try to flush when the user leaves the page
window.addEventListener('beforeunload', () => {
    if (pendingSolveQueue.length > 0) {
        // Use keepalive for page unloads
        fetch(`${API_BASE_URL}/api/solve_course`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ solves: pendingSolveQueue }),
            keepalive: true
        }).catch(e => console.error(e));
    }
});

async function mongoUpdateCourse(courseId, update) {
    return new Promise((resolve, reject) => {
        // 1. Write to localStorage FIRST — instant UI response, zero network delay
        lsSetSolve(courseId, update);

        // 2. Add to the background queue with the user's ID
        pendingSolveQueue.push({
            id: courseId,
            update: update,
            by: currentUserId
        });

        // 3. Resolve immediately so the UI doesn't hang waiting for the batch
        resolve({ status: 'queued' });
    });
}

// ── Loader helpers ────────────────────────────────────────────────

function setLoaderSub(text) {
    const el = document.getElementById('loader-sub');
    if (el) el.textContent = text;
}

function setConnStatus(state) {
    const dot = document.getElementById('conn-dot');
    const label = document.getElementById('conn-label');
    if (!dot || !label) return;
    dot.className = 'status-dot ' + state;
    label.textContent = state === 'connected' ? 'Connected'
        : state === 'error' ? 'Error'
            : 'Connecting';
}

// ── INIT ──────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    initTheme();
    initTabs();

    // Fetch data from Vercel API
    try {
        setConnStatus('connecting');
        allCourses = await fetchAllCourses();
        setConnStatus('connected');

        document.getElementById('loading-screen').style.display = 'none';
        document.getElementById('main-page').style.display = 'block';

        // Populate dropdowns
        populateFilters();

        // Wire up ALL interactivity FIRST, before any rendering. A failure
        // in a render (e.g. Chart.js failing to load from the CDN) must never
        // leave the page with unbound filters / dead controls.
        initFilters();
        initModal();
        initFeesTab();

        initKpiClickThrough();
        initSorting();
        initTopbarExtras();
        initSuggestions();
        startMotivationRotation();

        // Render every tab. Each is isolated so one failing renderer
        // (charts, lists, etc.) doesn't abort the rest of the page.
        safeRender(renderDashboard, 'renderDashboard');
        safeRender(renderVerificationTab, 'renderVerificationTab');
        safeRender(renderCoursesTab, 'renderCoursesTab');
        safeRender(renderSolvedTab, 'renderSolvedTab');

    } catch (err) {
        setConnStatus('error');
        setLoaderSub('Connection failed: ' + err.message);
        console.error('[MongoFetch]', err);
    }
});

// Run a renderer in isolation so a throw doesn't break sibling renders.
function safeRender(fn, name) {
    try { fn(); }
    catch (err) { console.error('[' + name + ']', err); }
}

// ── THEME ─────────────────────────────────────────────────────────

function initTheme() {
    const saved = localStorage.getItem('cv_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    updateThemeIcon(saved);

    document.getElementById('theme-btn').addEventListener('click', () => {
        const cur = document.documentElement.getAttribute('data-theme');
        const next = cur === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('cv_theme', next);
        updateThemeIcon(next);
        // Re-render charts with new colours
        renderDashboard();
    });
}

function updateThemeIcon(theme) {
    const el = document.getElementById('theme-icon');
    if (el) el.textContent = theme === 'dark' ? '☀' : '🌙';
}

// ── TABS ──────────────────────────────────────────────────────────

function initTabs() {
    document.getElementById('nav-tabs').addEventListener('click', e => {
        const link = e.target.closest('.nav-tab');
        if (!link) return;
        e.preventDefault();
        const target = link.dataset.tab;
        document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
        link.classList.add('active');
        document.getElementById(target).classList.add('active');
        setPageTitle(link.dataset.title, link.dataset.sub);
        // Lazy-load fees data on first visit to the Fees tab
        if (target === 'tab-fees' && feesData.length === 0) { loadFeesData(); }
    });
}

function initSorting() {
    document.querySelectorAll('th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const tableId = th.closest('tbody') ? th.closest('tbody').id : th.closest('table').querySelector('tbody').id;
            const prefix = tableId.split('-')[0]; // vf, cf, sf
            const col = th.dataset.sort;
            if (sortState[prefix].col === col) {
                sortState[prefix].dir *= -1; // toggle
            } else {
                sortState[prefix].col = col;
                sortState[prefix].dir = 1;
            }
            // update UI arrows
            th.closest('tr').querySelectorAll('th.sortable').forEach(t => {
                t.textContent = t.textContent.replace(' ↑', ' ↕').replace(' ↓', ' ↕');
            });
            th.textContent = th.textContent.replace(' ↕', sortState[prefix].dir === 1 ? ' ↑' : ' ↓');
            
            if (prefix === 'vf') renderVerificationTab();
            if (prefix === 'cf') renderCoursesTab();
            if (prefix === 'sf') renderSolvedTab();
        });
    });
}

// ── POPULATE FILTER DROPDOWNS ─────────────────────────────────────

function populateFilters() {
    const countries = [...new Set(allCourses.map(c => c.country).filter(Boolean))].sort();
    const domains = DOMAIN_RANGES.map(r => r.label);
    const courseTypes = [...new Set(allCourses.map(c => c.domain).filter(Boolean))].sort();

    ['vf-country', 'cf-country'].forEach(id => {
        const sel = document.getElementById(id);
        countries.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c; opt.textContent = c;
            sel.appendChild(opt);
        });
    });

    ['vf-domain', 'cf-domain', 'sf-domain'].forEach(id => {
        const sel = document.getElementById(id);
        domains.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d; opt.textContent = d;
            sel.appendChild(opt);
        });
    });
    
    ['vf-courseType', 'cf-courseType', 'sf-courseType'].forEach(id => {
        const sel = document.getElementById(id);
        courseTypes.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d; opt.textContent = d;
            sel.appendChild(opt);
        });
    });
}

// ── FILTER EVENTS ─────────────────────────────────────────────────

function initFilters() {
    let vfTimer, cfTimer, sfTimer;

    // Verification tab
    document.getElementById('vf-search').addEventListener('input', e => {
        clearTimeout(vfTimer);
        vfTimer = setTimeout(() => { vfFilter.search = e.target.value.toLowerCase(); vfPage = 1; renderVerificationTab(); }, 220);
    });
    document.getElementById('vf-status').addEventListener('change', e => { vfFilter.status = e.target.value; vfPage = 1; renderVerificationTab(); });
    document.getElementById('vf-country').addEventListener('change', e => { vfFilter.country = e.target.value; vfPage = 1; renderVerificationTab(); });
    document.getElementById('vf-domain').addEventListener('change', e => { vfFilter.domain = e.target.value; vfPage = 1; renderVerificationTab(); });
    document.getElementById('vf-courseType').addEventListener('change', e => { vfFilter.courseType = e.target.value; vfPage = 1; renderVerificationTab(); });
    document.getElementById('vf-reset').addEventListener('click', () => {
        vfFilter = { search: '', status: 'issues', country: 'all', domain: 'all', courseType: 'all' };
        document.getElementById('vf-search').value = '';
        document.getElementById('vf-status').value = 'issues';
        document.getElementById('vf-country').value = 'all';
        document.getElementById('vf-domain').value = 'all';
        document.getElementById('vf-courseType').value = 'all';
        vfPage = 1;
        renderVerificationTab();
    });

    // All Courses tab
    document.getElementById('cf-search').addEventListener('input', e => {
        clearTimeout(cfTimer);
        cfTimer = setTimeout(() => { cfFilter.search = e.target.value.toLowerCase(); cfPage = 1; renderCoursesTab(); }, 220);
    });
    document.getElementById('cf-status').addEventListener('change', e => { cfFilter.status = e.target.value; cfPage = 1; renderCoursesTab(); });
    document.getElementById('cf-country').addEventListener('change', e => { cfFilter.country = e.target.value; cfPage = 1; renderCoursesTab(); });
    document.getElementById('cf-domain').addEventListener('change', e => { cfFilter.domain = e.target.value; cfPage = 1; renderCoursesTab(); });
    document.getElementById('cf-courseType').addEventListener('change', e => { cfFilter.courseType = e.target.value; cfPage = 1; renderCoursesTab(); });
    document.getElementById('cf-qs').addEventListener('change', e => { cfFilter.qs = e.target.value; cfPage = 1; renderCoursesTab(); });
    document.getElementById('cf-reset').addEventListener('click', () => {
        cfFilter = { search: '', status: 'all', country: 'all', domain: 'all', qs: 'any', courseType: 'all' };
        document.getElementById('cf-search').value = '';
        document.getElementById('cf-status').value = 'all';
        document.getElementById('cf-country').value = 'all';
        document.getElementById('cf-domain').value = 'all';
        document.getElementById('cf-courseType').value = 'all';
        document.getElementById('cf-qs').value = 'any';
        cfPage = 1;
        renderCoursesTab();
        renderSolvedTab();
    });

    // Pagination
    document.getElementById('vf-prev').addEventListener('click', () => { if (vfPage > 1) { vfPage--; renderVerificationTab(); } });
    document.getElementById('vf-next').addEventListener('click', () => { vfPage++; renderVerificationTab(); });
    document.getElementById('cf-prev').addEventListener('click', () => { if (cfPage > 1) { cfPage--; renderCoursesTab(); } });
    document.getElementById('cf-next').addEventListener('click', () => { cfPage++; renderCoursesTab(); });

    // Solved Courses Tab
    document.getElementById('sf-search').addEventListener('input', e => {
        clearTimeout(sfTimer);
        sfTimer = setTimeout(() => { sfFilter.search = e.target.value.toLowerCase(); sfPage = 1; renderSolvedTab(); }, 220);
    });
    document.getElementById('sf-domain').addEventListener('change', e => { sfFilter.domain = e.target.value; sfPage = 1; renderSolvedTab(); });
    document.getElementById('sf-courseType').addEventListener('change', e => { sfFilter.courseType = e.target.value; sfPage = 1; renderSolvedTab(); });
    document.getElementById('sf-reset').addEventListener('click', () => {
        document.getElementById('sf-search').value = '';
        document.getElementById('sf-domain').value = 'all';
        document.getElementById('sf-courseType').value = 'all';
        sfFilter = { search: '', domain: 'all', courseType: 'all' };
        sfPage = 1;
        renderSolvedTab();
    });
    document.getElementById('sf-prev').addEventListener('click', () => { if (sfPage > 1) { sfPage--; renderSolvedTab(); } });
    document.getElementById('sf-next').addEventListener('click', () => { sfPage++; renderSolvedTab(); });
}

// ── KPI click-through to Verification tab ────────────────────────
function initKpiClickThrough() {
    document.getElementById('kpi-disc-card').addEventListener('click', () => {
        vfFilter.status = 'Discrepancy'; vfPage = 1;
        document.getElementById('vf-status').value = 'Discrepancy';
        document.querySelector('.nav-tab[data-tab="tab-verification"]').click();
        renderVerificationTab();
    });
    document.getElementById('kpi-err-card').addEventListener('click', () => {
        vfFilter.status = 'Error'; vfPage = 1;
        document.getElementById('vf-status').value = 'Error';
        document.querySelector('.nav-tab[data-tab="tab-verification"]').click();
        renderVerificationTab();
    });
}

// ── DASHBOARD ─────────────────────────────────────────────────────

function renderDashboard() {
    const total = allCourses.length;
    const verified = allCourses.filter(c => c.status === 'Verified').length;
    const disc = allCourses.filter(c => c.status === 'Discrepancy').length;
    const err = allCourses.filter(c => c.status === 'Error').length;
    const pct = total ? Math.round((verified / total) * 100) : 0;

    setText('kpi-total', total.toLocaleString());
    setText('kpi-verified', verified.toLocaleString());
    setText('kpi-verified-pct', `${pct}% of total`);
    setText('kpi-disc', disc.toLocaleString());
    setText('kpi-err', err.toLocaleString());

    renderDomainChart();
    renderStatusDonut(verified, disc, err);
    renderCountryList();
    renderRecentSolved();
    renderCorrectionsChart();
}

function renderRecentSolved() {
    const tbody = document.getElementById('recent-tbody');
    if (!tbody) return;
    let solved = [];
    if (window.globalPendingSolves && window.globalPendingSolves.length > 0) {
        const seen = new Set();
        for (const s of window.globalPendingSolves) {
            if (!seen.has(s.id)) {
                seen.add(s.id);
                const c = allCourses.find(x => x.id == s.id);
                if (c) solved.push(c);
            }
            if (solved.length >= 8) break;
        }
    } else {
        solved = allCourses
            .filter(c => c.solved_attrs && c.solved_attrs.length > 0)
            .slice(0, 8);
    }

    if (!solved.length) {
        tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No solved courses yet. Start the streak — Panvel awaits!</td></tr>';
        return;
    }

    tbody.innerHTML = solved.map(c => {
        let badge = '<span class="badge-status">' + escHtml(c.status || '—') + '</span>';
        if (c.status === 'Verified') badge = '<span class="badge-status status-ver">Verified</span>';
        else if (c.status === 'Discrepancy') badge = '<span class="badge-status status-disc">Disc. Resolved</span>';
        else if (c.status === 'Error') badge = '<span class="badge-status status-err">Error</span>';
        return `
            <tr onclick="openModal(${c.id})" title="Click to view details">
                <td class="course-id">#${escHtml(c.id)}</td>
                <td class="course-name" title="${escHtml(c.name)}">${escHtml(c.name)}</td>
                <td title="${escHtml(c.university)}">${escHtml(c.university || '—')}</td>
                <td>${badge}</td>
            </tr>
        `;
    }).join('');
}

function renderDomainChart() {
    if (typeof Chart === 'undefined') return;   // Chart.js (CDN) not loaded — skip gracefully
    const counts = {};
    DOMAIN_RANGES.forEach(r => { counts[r.label] = 0; });
    allCourses.forEach(c => {
        const lbl = getDomainLabel(c.id);
        if (c.status !== 'Verified') {
            counts[lbl] = (counts[lbl] || 0) + 1;
        }
    });

    const labels = Object.keys(counts);
    const data = Object.values(counts);
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    const textCol = isDark ? '#94a3b8' : '#64748b';
    const gridCol = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';

    const ctx = document.getElementById('domainBarChart').getContext('2d');
    if (domainChart) domainChart.destroy();

    domainChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: 'rgba(239,68,68,0.75)',
                borderColor: 'rgba(239,68,68,1)',
                borderWidth: 0,
                borderRadius: 6,
                hoverBackgroundColor: 'rgba(239,68,68,0.95)',
            }],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => ` ${ctx.raw.toLocaleString()} left` } } },
            scales: {
                x: { ticks: { color: textCol, font: { size: 11 } }, grid: { color: gridCol } },
                y: { ticks: { color: textCol, font: { size: 11 } }, grid: { color: gridCol }, beginAtZero: true },
            },
        },
    });
}

function renderStatusDonut(verified, disc, err) {
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    const textCol = isDark ? '#94a3b8' : '#64748b';

    // Donut chart — only if Chart.js (CDN) loaded
    if (typeof Chart !== 'undefined') {
        const ctxEl = document.getElementById('statusDonut');
        if (ctxEl) {
            const ctx = ctxEl.getContext('2d');
            if (statusChart) statusChart.destroy();
            statusChart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['Verified', 'Discrepancy', 'Error'],
                    datasets: [{
                        data: [verified, disc, err],
                        backgroundColor: ['rgba(34,197,94,0.75)', 'rgba(245,158,11,0.75)', 'rgba(239,68,68,0.75)'],
                        borderColor: ['#22c55e', '#f59e0b', '#ef4444'],
                        borderWidth: 2,
                        hoverOffset: 8,
                    }],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    cutout: '68%',
                    plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.raw.toLocaleString()}` } } },
                },
            });
        }
    }

    // Custom legend — plain HTML, renders even without Chart.js
    const legend = document.getElementById('donut-legend');
    if (legend) {
        const total = verified + disc + err;
        legend.innerHTML = [
            { label: 'Verified', color: '#22c55e', val: verified },
            { label: 'Discrepancy', color: '#f59e0b', val: disc },
            { label: 'Error', color: '#ef4444', val: err },
        ].map(i => `
            <div class="donut-legend-item">
                <div class="donut-dot" style="background:${i.color}"></div>
                ${i.label} — ${i.val.toLocaleString()} (${total ? Math.round((i.val / total) * 100) : 0}%)
            </div>
        `).join('');
    }
}

function renderCorrectionsChart() {
    if (typeof Chart === 'undefined') return;
    const ctxEl = document.getElementById('correctionsChart');
    if (!ctxEl) return;

    // Helper: local YYYY-MM-DD so late-night India solves don't show as "yesterday"
    function localDateKey(d) {
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    }

    function parseLocalDate(key) {
        const [y, m, d] = key.split('-').map(Number);
        return new Date(y, m - 1, d);
    }

    // Group solved courses by date
    const counts = {};
    allCourses.forEach(c => {
        if (!c.solved_ts) return;
        const d = new Date(c.solved_ts);
        if (isNaN(d.getTime())) return;
        const key = localDateKey(d);
        counts[key] = (counts[key] || 0) + 1;
    });

    // Build a contiguous calendar range ending today
    const today = new Date();
    const todayKey = localDateKey(today);
    const solvedKeys = Object.keys(counts);
    let startKey = todayKey;
    if (solvedKeys.length) {
        const earliest = solvedKeys.sort()[0];
        if (earliest < startKey) startKey = earliest;
    }

    const labels = [];
    const data = [];
    const bgColors = [];
    const start = parseLocalDate(startKey);
    const end = parseLocalDate(todayKey);
    for (let cur = new Date(start); cur <= end; cur.setDate(cur.getDate() + 1)) {
        const key = localDateKey(cur);
        const count = counts[key] || 0;
        labels.push(key.slice(5));          // show MM-DD on the axis
        data.push(count);
        bgColors.push(key === todayKey
            ? 'rgba(0,229,255,0.85)'        // highlight today
            : 'rgba(34,197,94,0.75)');
    }

    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    const textCol = isDark ? '#94a3b8' : '#64748b';
    const gridCol = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';

    if (correctionsChart) correctionsChart.destroy();

    correctionsChart = new Chart(ctxEl.getContext('2d'), {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Corrections',
                data,
                backgroundColor: bgColors,
                borderColor: bgColors.map(c => c.replace('0.75', '1').replace('0.85', '1')),
                borderWidth: 0,
                borderRadius: 5,
                hoverBackgroundColor: bgColors.map(c => c.replace('0.75', '0.95').replace('0.85', '1')),
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: items => {
                            const idx = items[0].dataIndex;
                            const baseYear = labels[idx].startsWith(todayKey.slice(0, 4)) ? todayKey.slice(0, 5) : String(today.getFullYear() - 1) + '-';
                            return baseYear + labels[idx];
                        },
                        label: ctx => ` ${ctx.raw.toLocaleString()} corrected`,
                    },
                },
            },
            scales: {
                x: { ticks: { color: textCol, font: { size: 11 } }, grid: { color: gridCol } },
                y: { ticks: { color: textCol, font: { size: 11 } }, grid: { color: gridCol }, beginAtZero: true },
            },
        },
    });
}

function renderCountryList() {
    const counts = {};
    allCourses.forEach(c => {
        if (c.country) counts[c.country] = (counts[c.country] || 0) + 1;
    });

    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 15);
    const max = sorted[0]?.[1] || 1;

    document.getElementById('country-list').innerHTML = sorted.map(([name, count], i) => `
        <div class="country-row">
            <div class="country-flag">${countryFlag(name)}</div>
            <div class="country-rank">${i + 1}</div>
            <div class="country-name" title="${escHtml(name)}">${escHtml(name)}</div>
            <div class="country-bar-wrap">
                <div class="country-bar" style="width:${Math.round((count / max) * 100)}%"></div>
            </div>
            <div class="country-count">${count}</div>
        </div>
    `).join('');
}

// ── VERIFICATION TAB ──────────────────────────────────────────────

function applyVfFilter(courses) {
    const { search, status, country, domain, courseType } = vfFilter;
    return courses.filter(c => {
        if (status === 'issues') { if (c.status === 'Verified') return false; }
        else if (status !== 'all') { if (c.status !== status) return false; }
        if (country !== 'all' && c.country !== country) return false;
        if (domain !== 'all' && getDomainLabel(c.id) !== domain) return false;
        if (courseType && courseType !== 'all' && (c.domain || 'Uncategorised') !== courseType) return false;
        if (search) {
            if (/^\d+$/.test(search)) {
                if (String(c.id) !== search) return false;
            } else {
                const hay = `${c.name} ${c.university} ${c.country} ${c.disc_reason}`.toLowerCase();
                if (!hay.includes(search)) return false;
            }
        }
        return true;
    });
}

function renderVerificationTab() {
    let filtered = applyVfFilter(allCourses);
    filtered = sortCourses(filtered, sortState.vf);
    const total = filtered.length;
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    if (vfPage > totalPages) vfPage = totalPages;
    const slice = filtered.slice((vfPage - 1) * PAGE_SIZE, vfPage * PAGE_SIZE);

    // Table
    const tbody = document.getElementById('vf-tbody');
    if (!slice.length) {
        tbody.innerHTML = '<tr><td colspan="10" class="empty-state">No courses match the current filters. All caught up — time for chai (or Panvel prep).</td></tr>';
    } else {
        tbody.innerHTML = slice.map((c, i) => `
            <tr onclick="openModal('${c.id}')">
                <td>${(vfPage - 1) * PAGE_SIZE + i + 1}</td>
                <td style="color:var(--text-muted);font-size:0.8rem;white-space:nowrap;">${c.pdf_page ? 'Pg ' + c.pdf_page : '-'}</td>
                <td title="${escHtml(c.name)}">${escHtml(c.name)}</td>
                <td title="${escHtml(c.university)}">${escHtml(c.university || '—')}</td>
                <td>${escHtml(c.country || '—')}</td>
                <td><span style="font-size:0.78rem; color:var(--text-muted);">${getDomainLabel(c.id)}</span></td>
                <td><span style="font-size:0.78rem; color:var(--text-muted);">${escHtml(c.domain || 'Uncategorised')}</span></td>
                <td>${escHtml(c.mode || '—')}</td>
                <td>${badgeHtml(c.status)}</td>
                <td style="font-size:0.78rem; color:var(--text-muted);" title="${escHtml(c.disc_reason || c.issue_sub_type || '')}">${escHtml(c.disc_reason || c.issue_sub_type || '—')}</td>
            </tr>
        `).join('');
    }

    // Pagination
    setText('vf-pag-info', `Page ${vfPage} of ${totalPages} (${total.toLocaleString()} courses)`);
    document.getElementById('vf-prev').disabled = vfPage <= 1;
    document.getElementById('vf-next').disabled = vfPage >= totalPages;
}

// ── ALL COURSES TAB ───────────────────────────────────────────────

function applyCfFilter(courses) {
    const { search, status, country, domain, qs, courseType } = cfFilter;
    return courses.filter(c => {
        if (status !== 'all' && c.status !== status) return false;
        if (country !== 'all' && c.country !== country) return false;
        if (domain !== 'all' && getDomainLabel(c.id) !== domain) return false;
        if (courseType && courseType !== 'all' && (c.domain || 'Uncategorised') !== courseType) return false;
        if (qs === 'yes' && !c.has_qs_badge) return false;
        if (qs === 'no' && c.has_qs_badge) return false;
        if (search) {
            if (/^\d+$/.test(search)) {
                if (String(c.id) !== search) return false;
            } else {
                const hay = `${c.name} ${c.university} ${c.country} ${c.skills || ''}`.toLowerCase();
                if (!hay.includes(search)) return false;
            }
        }
        return true;
    });
}

function renderSolvedTab() {
    let filtered = allCourses.filter(c => c.solved_attrs && c.solved_attrs.length > 0);
    
    if (sfFilter.search) {
        const q = sfFilter.search;
        filtered = filtered.filter(c => {
            if (/^\d+$/.test(q)) {
                return String(c.id) === q;
            } else {
                return (c.name || '').toLowerCase().includes(q) ||
                       (c.university || '').toLowerCase().includes(q) ||
                       (c.country || '').toLowerCase().includes(q);
            }
        });
    }
    
    if (sfFilter.domain && sfFilter.domain !== 'all') {
        filtered = filtered.filter(c => getDomainLabel(c.id) === sfFilter.domain);
    }
    
    if (sfFilter.courseType && sfFilter.courseType !== 'all') {
        filtered = filtered.filter(c => c.domain === sfFilter.courseType);
    }
    
    const total = filtered.length;
    const totalPages = Math.ceil(total / PAGE_SIZE) || 1;
    if (sfPage > totalPages) sfPage = totalPages;
    
    document.getElementById('sf-pag-info').textContent = `Page ${sfPage} of ${totalPages} (${total} total)`;
    document.getElementById('sf-prev').disabled = sfPage === 1;
    document.getElementById('sf-next').disabled = sfPage === totalPages;
    
    filtered = sortCourses(filtered, sortState.sf);
    
    const start = (sfPage - 1) * PAGE_SIZE;
    const end = start + PAGE_SIZE;
    const pageData = filtered.slice(start, end);
    const tbody = document.getElementById('sf-tbody');
    tbody.innerHTML = '';
    
    if (pageData.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="empty-state">No solved courses yet! Every fix is a step closer to a clean catalog.</td></tr>`;
        return;
    }
    
    pageData.forEach(c => {
        const domLabel = getDomainLabel(c.id);
        const tr = document.createElement('tr');
        tr.onclick = () => openModal(c.id);
        
        let statBadge = '';
        if (c.status === 'Verified') statBadge = `<span class="badge-status status-ver">Verified</span>`;
        else if (c.status === 'Discrepancy') statBadge = `<span class="badge-status status-disc">Discrepancy</span>`;
        else if (c.status === 'Error') statBadge = `<span class="badge-status status-err">Error</span>`;
        else statBadge = `<span class="badge-status">${c.status || '—'}</span>`;
        
        let solvedAtStr = '-';
        if (c.solved_ts) {
            solvedAtStr = new Date(c.solved_ts).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        }

        tr.innerHTML = `
            <td style="color:var(--text-dim); font-size:0.8rem;">${c.id}</td>
            <td style="color:var(--text-dim);font-size:0.8rem;white-space:nowrap;">${c.pdf_page ? 'Pg ' + c.pdf_page : '-'}</td>
            <td class="td-name">${escHtml(c.name)}</td>
            <td>${escHtml(c.university)}</td>
            <td>${escHtml(c.country || '—')}</td>
            <td><span class="badge-domain">${domLabel}</span></td>
            <td><span style="font-size:0.78rem; color:var(--text-muted);">${escHtml(c.domain || 'Uncategorised')}</span></td>
            <td>${escHtml(c.mode || '—')}</td>
            <td><span style="color:var(--text-muted); font-size:0.85rem;">${solvedAtStr}</span></td>
            <td>${statBadge}</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderCoursesTab() {
    let filtered = applyCfFilter(allCourses);
    filtered = sortCourses(filtered, sortState.cf);
    const total = filtered.length;
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    if (cfPage > totalPages) cfPage = totalPages;
    const slice = filtered.slice((cfPage - 1) * PAGE_SIZE, cfPage * PAGE_SIZE);

    const tbody = document.getElementById('cf-tbody');
    if (!slice.length) {
        tbody.innerHTML = '<tr><td colspan="10" class="empty-state">No courses match the current filters. All caught up — time for chai (or Panvel prep).</td></tr>';
    } else {
        tbody.innerHTML = slice.map((c, i) => `
            <tr onclick="openModal('${c.id}')">
                <td>${(cfPage - 1) * PAGE_SIZE + i + 1}</td>
                <td style="color:var(--text-muted);font-size:0.8rem;white-space:nowrap;">${c.pdf_page ? 'Pg ' + c.pdf_page : '-'}</td>
                <td title="${escHtml(c.name)}">${escHtml(c.name)}</td>
                <td title="${escHtml(c.university)}">${escHtml(c.university || '—')}</td>
                <td>${escHtml(c.country || '—')}</td>
                <td><span style="font-size:0.78rem; color:var(--text-muted);">${getDomainLabel(c.id)}</span></td>
                <td><span style="font-size:0.78rem; color:var(--text-muted);">${escHtml(c.domain || 'Uncategorised')}</span></td>
                <td>${c.has_qs_badge ? '<span class="badge" style="background:var(--blue-bg);color:var(--blue);border:1px solid rgba(59,130,246,0.25);">QS ✓</span>' : '—'}</td>
                <td>${badgeHtml(c.status)}</td>
            </tr>
        `).join('');
    }

    setText('cf-pag-info', `Page ${cfPage} of ${totalPages} (${total.toLocaleString()} courses)`);
    document.getElementById('cf-prev').disabled = cfPage <= 1;
    document.getElementById('cf-next').disabled = cfPage >= totalPages;
}

// ── MODAL ─────────────────────────────────────────────────────────

function initModal() {
    document.getElementById('modal-close').addEventListener('click', closeModal);
    document.getElementById('course-modal').addEventListener('click', e => {
        if (e.target === e.currentTarget) closeModal();
    });
    document.getElementById('modal-solve-all').addEventListener('click', solveAll);
}

async function openModal(courseId) {
    const cBase = allCourses.find(x => x.id == courseId);
    if (!cBase) return;

    // Show loading state while fetching heavy details
    setText('modal-title', cBase.name || '—');
    setText('modal-sub', 'Fetching details from database...');
    document.getElementById('modal-meta').innerHTML = '';
    document.getElementById('modal-tbody').innerHTML = '<tr><td colspan="5" class="empty-state">Loading comparison data...</td></tr>';
    document.getElementById('course-modal').classList.add('open');

    try {
        const c = cBase;
        modalCourse = c;

        setText('modal-sub', `${c.university || '—'}  ·  ${c.country || '—'}  ·  Page ${c.pdf_page || '?'}`);

        // Badge
        const badge = document.getElementById('modal-badge');
        badge.className = 'badge badge-' + (c.status || '').toLowerCase();
        badge.textContent = c.status || '—';

        // Meta chips
        document.getElementById('modal-meta').innerHTML = [
            ['Cost', c.cost],
            ['Duration', c.duration],
            ['Mode', c.mode],
            ['Domain', getDomainLabel(c.id)],
            ['QS', c.has_qs_badge ? '✓ Ranked' : '—'],
            ['NIRF', c.has_nirf_badge ? '✓ Ranked' : '—'],
        ].map(([k, v]) => `<div class="meta-chip"><strong>${k}:</strong> ${escHtml(String(v || '—'))}</div>`).join('');

        // ── Pill buttons: Course Link + Fee Structure ────────────────────────
        const linkBtn = document.getElementById('modal-link-btn');
        if (linkBtn) {
            if (c.url) {
                linkBtn.href = c.url;
                linkBtn.style.display = 'flex';
            } else {
                linkBtn.style.display = 'none';
            }
        }

        // Fee Structure button – only when fee link exists AND is a different
        // URL than the main course link (i.e. a dedicated fees page)
        

        // Comparison table
        const rows = c.pdf_table || [];
        const solved = c.solved_attrs || [];
        const hasMismatch = rows.some(r => r.original !== r.verified);

        if (!rows.length) {
            document.getElementById('modal-tbody').innerHTML = '<tr><td colspan="5" class="empty-state">No comparison data available.</td></tr>';
        } else {
            document.getElementById('modal-tbody').innerHTML = rows.map(r => {
                const isSolved = solved.includes(r.attribute?.toLowerCase());
                const isMismatch = r.status ? (r.status.toUpperCase() !== 'MATCH') : (r.original !== r.verified);
                const rowClass = isSolved ? 'solved-row' : isMismatch ? 'mismatch-row' : '';
                const matchIcon = isMismatch
                    ? '<span class="match-icon match-no">✕</span>'
                    : '<span class="match-icon match-yes">✓</span>';
                const btn = isMismatch
                    ? `<button class="btn-solve ${isSolved ? 'solved' : ''}"
                           onclick="solveAttr(${c.id}, '${escJs(r.attribute)}', ${isSolved})"
                           title="${isSolved ? 'Undo resolve' : 'Mark as resolved'}">
                           ${isSolved ? '✓ Solved' : 'Solve'}
                       </button>`
                    : '<span style="color:var(--text-dim); font-size:0.78rem;">OK</span>';
                return `<tr class="${rowClass}">
                    <td>${escHtml(r.attribute || '—')}</td>
                    <td>${escHtml(r.original || '—')}</td>
                    <td>${escHtml(r.verified || '—')}</td>
                    <td>${matchIcon}</td>
                    <td>${btn}</td>
                </tr>`;
            }).join('');
        }

        // Hint + Solve All button
        const allSolved = rows.every(r => {
            const isMismatch = r.status ? (r.status.toUpperCase() !== 'MATCH') : (r.original !== r.verified);
            return !isMismatch || solved.includes(r.attribute?.toLowerCase());
        });
        document.getElementById('modal-hint').textContent = c.disc_reason || '';
        const solveAllBtn = document.getElementById('modal-solve-all');
        solveAllBtn.classList.toggle('visible', hasMismatch);
        if (allSolved) {
            solveAllBtn.textContent = '✗ Unsolve All';
            solveAllBtn.classList.add('unsolve');
        } else {
            solveAllBtn.textContent = '✓ Mark All Resolved';
            solveAllBtn.classList.remove('unsolve');
        }

    } catch (err) {
        document.getElementById('modal-tbody').innerHTML = `<tr><td colspan="5" class="empty-state" style="color:var(--red)">Error loading details: ${err.message}</td></tr>`;
    }
}

function closeModal() {
    document.getElementById('course-modal').classList.remove('open');
    modalCourse = null;
}

// ── SOLVE ─────────────────────────────────────────────────────────

function refreshKPIs() {
    const verified = allCourses.filter(x => x.status === 'Verified').length;
    const disc = allCourses.filter(x => x.status === 'Discrepancy').length;
    const err = allCourses.filter(x => x.status === 'Error').length;
    const total = allCourses.length;
    if (total === 0) return;
    setText('kpi-verified', verified.toLocaleString());
    setText('kpi-verified-pct', `${Math.round((verified / total) * 100)}% of total`);
    setText('kpi-disc', disc.toLocaleString());
    setText('kpi-err', err.toLocaleString());
    if (typeof renderStatusDonut === 'function') {
        renderStatusDonut(verified, disc, err);
    }
    if (typeof renderDomainChart === 'function') renderDomainChart();
    if (typeof renderCorrectionsChart === 'function') renderCorrectionsChart();
}

async function solveAttr(courseId, attr, isSolved) {
    const c = allCourses.find(x => x.id == courseId);
    if (!c) return;

    let solved = [...(c.solved_attrs || [])];
    const key = attr.toLowerCase();

    if (isSolved) {
        // Undo: remove from solved list
        solved = solved.filter(s => s !== key);
    } else {
        // Solve: add to solved list
        if (!solved.includes(key)) solved.push(key);
    }

    // Determine new status: if all mismatched attrs are solved → Verified
    const rows = c.pdf_table || [];
    const mismatchAttrs = rows
        .filter(r => r.status ? (r.status.toUpperCase() !== 'MATCH') : (r.original !== r.verified))
        .map(r => r.attribute?.toLowerCase());
    const allSolved = mismatchAttrs.every(a => solved.includes(a));

    const newStatus = allSolved ? 'Verified' : getOriginalStatus(c);
    const newCategory = allSolved ? 'verified' : getOriginalCategory(c);

    const update = {
        solved_attrs: solved,
        status: newStatus,
        issue_category: newCategory,
        solved_ts: Date.now()
    };

    // Save original state so we can roll back on save failure
    const originalState = {
        solved_attrs: [...(c.solved_attrs || [])],
        status: c.status,
        issue_category: c.issue_category,
    };

    // Optimistic local update
    Object.assign(c, update);

    // Refresh UI immediately (Optimistic)
    openModal(courseId);
    renderVerificationTab();
    renderCoursesTab();
    renderSolvedTab();
    renderRecentSolved();
    refreshKPIs();

    // Prompt to solve the same issue on duplicate courses / pages
    if (!isSolved) showSuggestionPopup(c, [key]);

    try {
        await mongoUpdateCourse(courseId, update);
        showToast('Issue resolved', `“${escHtml(attr)}” updated successfully. ${randomToastMotivation()}`, 'success');
    } catch (err) {
        // Revert optimistic update on failure
        Object.assign(c, originalState);
        // Refresh UI to reflect reverted state
        openModal(courseId);
        renderVerificationTab();
        renderCoursesTab();
        renderSolvedTab();
        renderRecentSolved();
        refreshKPIs();
        showToast('Save failed', err.message, 'error');
    }
}

async function solveAll() {
    if (!modalCourse) return;
    const c = modalCourse;
    const rows = c.pdf_table || [];
    
    const mismatchAttrs = rows
        .filter(r => r.status ? (r.status.toUpperCase() !== 'MATCH') : (r.original !== r.verified))
        .map(r => r.attribute?.toLowerCase()).filter(Boolean);
        
    const curSolved = c.solved_attrs || [];
    const allSolved = mismatchAttrs.every(a => curSolved.includes(a));
    
    let update;
    if (allSolved) {
        // Unsolve all! Restore original state
        update = {
            solved_attrs: [],
            status: getOriginalStatus(c),
            issue_category: getOriginalCategory(c),
        };
    } else {
        // Solve all
        update = {
            solved_attrs: mismatchAttrs,
            status: 'Verified',
            issue_category: 'verified',
            solved_ts: Date.now()
        };
    }
    // Save original state for rollback
    const originalState = {
        solved_attrs: [...(c.solved_attrs || [])],
        status: c.status,
        issue_category: c.issue_category,
    };

    Object.assign(c, update);

    // Refresh UI immediately (Optimistic)
    openModal(c.id);
    renderVerificationTab();
    renderCoursesTab();
    renderSolvedTab();
    renderRecentSolved();
    refreshKPIs();

    // If we just solved everything, prompt duplicates with the same issues
    if (!allSolved) showSuggestionPopup(c, mismatchAttrs);

    try {
        await mongoUpdateCourse(c.id, update);
        showToast(
            allSolved ? 'Course restored' : 'All issues resolved',
            allSolved ? `Course returned to original state. ${randomToastMotivation()}` : `All mismatched attributes marked as resolved. ${randomToastMotivation()}`,
            'success'
        );
    } catch (err) {
        Object.assign(c, originalState);
        openModal(c.id);
        renderVerificationTab();
        renderCoursesTab();
        renderSolvedTab();
        renderRecentSolved();
        refreshKPIs();
        showToast('Save failed', err.message, 'error');
    }
}

// ── SMART SUGGESTIONS (duplicate courses) ─────────────────────────

let suggestDuplicates = localStorage.getItem('cv_suggest_duplicates') !== 'false';

function initSuggestions() {
    const toggle = document.getElementById('suggest-toggle');
    if (toggle) {
        toggle.checked = suggestDuplicates;
        toggle.addEventListener('change', e => {
            suggestDuplicates = e.target.checked;
            localStorage.setItem('cv_suggest_duplicates', suggestDuplicates ? 'true' : 'false');
        });
    }

    const suggestModal = document.getElementById('suggest-modal');
    document.getElementById('suggest-close')?.addEventListener('click', closeSuggestions);
    document.getElementById('suggest-dismiss')?.addEventListener('click', closeSuggestions);
    suggestModal?.addEventListener('click', e => {
        if (e.target === suggestModal) closeSuggestions();
    });
}

function closeSuggestions() {
    const modal = document.getElementById('suggest-modal');
    if (modal) modal.classList.remove('open');
}

// ── Toast ─────────────────────────────────────────────────────────
let toastTimer = null;
function showToast(title, message, type = 'success') {
    const toast = document.getElementById('toast');
    if (!toast) return;
    document.getElementById('toast-title').textContent = title || 'Saved';
    document.getElementById('toast-msg').textContent = message || '';
    document.getElementById('toast-icon').textContent = type === 'error' ? '✕' : '✓';
    toast.className = 'toast ' + (type === 'error' ? 'toast-error' : '');
    // Force reflow so the transition fires if called again quickly
    void toast.offsetWidth;
    toast.classList.add('open');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('open'), 3200);
}

function normalizeMatch(str) {
    return String(str || '').toLowerCase().trim().replace(/\s+/g, ' ');
}

function getMismatchingRows(course) {
    const rows = course.pdf_table || [];
    return rows.filter(r => r.status ? (r.status.toUpperCase() !== 'MATCH') : (r.original !== r.verified));
}

function findDuplicateSuggestions(course, solvedAttrs) {
    const baseName = normalizeMatch(course.name);
    const baseUni = normalizeMatch(course.university);
    const baseCountry = normalizeMatch(course.country);
    const solvedSet = new Set((solvedAttrs || []).map(a => String(a).toLowerCase()));
    const out = [];

    for (const d of allCourses) {
        if (d.id == course.id) continue;
        if (normalizeMatch(d.name) !== baseName) continue;
        if (normalizeMatch(d.university) !== baseUni) continue;
        if (normalizeMatch(d.country) !== baseCountry) continue;
        if (d.pdf_page === course.pdf_page && d.domain === course.domain) continue;
        if (d.status === 'Verified') continue;

        const dupSolved = new Set((d.solved_attrs || []).map(s => String(s).toLowerCase()));
        const dupRows = getMismatchingRows(d);
        const matchingIssues = dupRows
            .filter(r => solvedSet.has(String(r.attribute).toLowerCase()) && !dupSolved.has(String(r.attribute).toLowerCase()))
            .map(r => r.attribute);

        if (matchingIssues.length) {
            out.push({ course: d, issues: [...new Set(matchingIssues)] });
        }
    }
    return out;
}

function showSuggestionPopup(course, solvedAttrs) {
    if (!suggestDuplicates) return;
    const suggestions = findDuplicateSuggestions(course, solvedAttrs);
    if (!suggestions.length) return;

    const list = document.getElementById('suggest-list');
    if (!list) return;

    list.innerHTML = suggestions.map(s => {
        const d = s.course;
        const issueBadges = s.issues.map(a => `<span class="badge badge-error" style="font-size:0.7rem;padding:2px 8px;">${escHtml(a)}</span>`).join(' ');
        return `
            <div class="suggest-item" onclick="openSuggestionCourse('${d.id}')">
                <div class="suggest-info">
                    <div class="suggest-name" title="${escHtml(d.name)}">${escHtml(d.name)}</div>
                    <div class="suggest-meta">
                        <span>${escHtml(d.domain || '—')}</span>
                        <span>·</span>
                        <span>Page ${escHtml(d.pdf_page || '?')}</span>
                        <span>·</span>
                        <span>${escHtml(d.university || '—')}</span>
                    </div>
                    <div class="suggest-issue">Unresolved issues: ${issueBadges}</div>
                </div>
                <button class="suggest-btn" onclick="event.stopPropagation(); openSuggestionCourse('${d.id}')">Solve</button>
            </div>
        `;
    }).join('');

    document.getElementById('suggest-modal')?.classList.add('open');
}

function openSuggestionCourse(courseId) {
    closeSuggestions();
    openModal(courseId);
}

// ── HELPERS ───────────────────────────────────────────────────────

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

// ── Page title (top bar) ────────────────────────────────────────
function setPageTitle(title, sub) {
    if (title) setText('page-title', title);
    if (sub !== undefined) setText('page-sub', sub);
}

// ── Country → flag emoji ────────────────────────────────────────
function countryFlag(name) {
    if (!name) return '🌐';
    const map = {
        'india': '🇮🇳', 'usa': '🇺🇸', 'united states': '🇺🇸', 'united states of america': '🇺🇸',
        'uk': '🇬🇧', 'united kingdom': '🇬🇧', 'britain': '🇬🇧', 'england': '🇬🇧',
        'australia': '🇦🇺', 'canada': '🇨🇦', 'germany': '🇩🇪', 'france': '🇫🇷',
        'ireland': '🇮🇪', 'netherlands': '🇳🇱', 'singapore': '🇸🇬', 'switzerland': '🇨🇭',
        'sweden': '🇸🇪', 'spain': '🇪🇸', 'italy': '🇮🇹', 'japan': '🇯🇵', 'china': '🇨🇳',
        'hong kong': '🇭🇰', 'south korea': '🇰🇷', 'korea': '🇰🇷', 'new zealand': '🇳🇿',
        'dubai': '🇦🇪', 'uae': '🇦🇪', 'united arab emirates': '🇦🇪', 'malaysia': '🇲🇾',
        'online': '🌐', 'remote': '🌐', 'global': '🌐',
    };
    const key = String(name).toLowerCase().trim();
    if (map[key]) return map[key];
    // Convert 2-letter ISO code to regional indicator flags
    if (/^[a-z]{2}$/i.test(name)) {
        const cc = name.toUpperCase();
        return String.fromCodePoint(...[...cc].map(c => 0x1f1e6 + c.charCodeAt(0) - 65));
    }
    return '🌐';
}

// ── Top-bar global search ───────────────────────────────────────
function initTopbarExtras() {
    // Global search routes to All Courses tab and filters
    let tbTimer;
    const tb = document.getElementById('topbar-search');
    if (tb) {
        tb.addEventListener('input', e => {
            clearTimeout(tbTimer);
            const q = e.target.value.toLowerCase();
            tbTimer = setTimeout(() => {
                if (!q) return;
                cfFilter.search = q; cfPage = 1;
                const cs = document.getElementById('cf-search');
                if (cs) cs.value = q;
                document.querySelector('.nav-tab[data-tab="tab-courses"]').click();
                renderCoursesTab();
            }, 250);
        });
    }

    // "View all" on Recently Solved → Solved Courses tab
    const recentLink = document.getElementById('recent-link');
    if (recentLink) {
        recentLink.addEventListener('click', e => {
            e.preventDefault();
            document.querySelector('.nav-tab[data-tab="tab-solved"]').click();
        });
    }
}

function escHtml(str) {
    return String(str || '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function escJs(str) {
    return String(str || '').replace(/'/g, "\\'").replace(/"/g, '\\"');
}

function badgeHtml(status) {
    const cls = {
        Verified: 'badge-verified',
        Discrepancy: 'badge-discrepancy',
        Error: 'badge-error',
    }[status] || 'badge-error';
    return `<span class="badge ${cls}">${escHtml(status || '—')}</span>`;
}


// ── FEES TAB ───────────────────────────────────────────────────────────────

let feesData = [];        // Loaded from fees_data.json once
let feesFiltered = [];    // After search/filter applied
let feesPage = 1;
const FEES_PAGE_SIZE = 100;
let feesSortCol = 'idx';
let feesSortDir = 1;

async function loadFeesData() {
    if (feesData.length > 0) return;
    try {
        const res = await fetch('fees_data.json');
        let allFees = await res.json();
        feesData = allFees.filter(r => r.fees_link && String(r.fees_link).trim() !== '' && String(r.fees_link).trim() !== '-');
        // Add original index for stable sorting
        feesData.forEach((r, i) => r._idx = i + 1);
        renderFeesTab();
    } catch(e) {
        document.getElementById('fees-tbody').innerHTML =
            '<tr><td colspan="4" class="empty-state">Could not load fees data.</td></tr>';
    }
}

function renderFeesTab() {
    const search = (document.getElementById('fees-search')?.value || '').toLowerCase().trim();
    feesFiltered = feesData.filter(r => {
        if (!search) return true;
        if (/^\d+$/.test(search)) {
            return String(r._idx) === search;
        }
        return r.institute.toLowerCase().includes(search) ||
               r.course.toLowerCase().includes(search);
    });

    // Sort
    feesFiltered.sort((a, b) => {
        let av, bv;
        if (feesSortCol === 'idx')       { av = a._idx; bv = b._idx; }
        else if (feesSortCol === 'institute') { av = a.institute; bv = b.institute; }
        else                             { av = a.course;    bv = b.course;    }
        if (av < bv) return -feesSortDir;
        if (av > bv) return  feesSortDir;
        return 0;
    });

    const total = feesFiltered.length;
    const totalPages = Math.max(1, Math.ceil(total / FEES_PAGE_SIZE));
    if (feesPage > totalPages) feesPage = totalPages;

    const slice = feesFiltered.slice((feesPage - 1) * FEES_PAGE_SIZE, feesPage * FEES_PAGE_SIZE);

    const tbody = document.getElementById('fees-tbody');
    if (!slice.length) {
        tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No results match your search. Try another keyword and keep the momentum going.</td></tr>';
    } else {
        tbody.innerHTML = slice.map((r, i) => `
            <tr onclick="window.open(\'${escHtml(r.fees_link)}\', \'_blank\')" style="cursor: pointer;" class="fee-row-hover">
                <td style="color:var(--text-dim);font-size:0.8rem;">${(feesPage-1)*FEES_PAGE_SIZE + i + 1}</td>
                <td style="font-size:0.85rem;">${escHtml(r.institute || '—')}</td>
                <td style="font-size:0.85rem;">${escHtml(r.course || '—')}</td>
                <td>${r.fees_link
                    ? `<a href="${escHtml(r.fees_link)}" target="_blank" rel="noopener noreferrer"
                          style="display:inline-flex;align-items:center;gap:5px;padding:3px 10px;
                                 border-radius:20px;background:rgba(34,197,94,0.15);
                                 border:1px solid rgba(34,197,94,0.4);color:#4ade80;
                                 font-size:0.76rem;font-weight:600;text-decoration:none;">
                           <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/><line x1="12" y1="12" x2="12" y2="16"/><line x1="10" y1="14" x2="14" y2="14"/></svg>
                           Fees
                        </a>`
                    : '<span style="color:var(--text-dim);font-size:0.78rem;">—</span>'
                }</td>
            </tr>
        `).join('');
    }

    document.getElementById('fees-pag-info').textContent =
        `Page ${feesPage} of ${totalPages} (${total.toLocaleString()} entries)`;
    document.getElementById('fees-prev').disabled = feesPage <= 1;
    document.getElementById('fees-next').disabled = feesPage >= totalPages;
}

function initFeesTab() {
    document.getElementById('fees-search').addEventListener('input', () => {
        feesPage = 1; renderFeesTab();
    });
    document.getElementById('fees-prev').addEventListener('click', () => {
        if (feesPage > 1) { feesPage--; renderFeesTab(); }
    });
    document.getElementById('fees-next').addEventListener('click', () => {
        const totalPages = Math.ceil(feesFiltered.length / FEES_PAGE_SIZE);
        if (feesPage < totalPages) { feesPage++; renderFeesTab(); }
    });

    document.querySelectorAll('[data-fees-sort]').forEach(th => {
        th.style.cursor = 'pointer';
        th.addEventListener('click', () => {
            const col = th.dataset.feesSort;
            if (feesSortCol === col) feesSortDir = -feesSortDir;
            else { feesSortCol = col; feesSortDir = 1; }
            feesPage = 1;
            renderFeesTab();
        });
    });
}


// ─────────────────────────────────────────────────────────────────
// SOLVE STORAGE: localStorage-first, Cloudflare write-through
//
// All solves are stored in localStorage under 'cv_solves'.
// Structure: { [courseId]: { update: {...}, ts: <unix ms> } }
//
// On page load: Cloudflare solves are merged INTO localStorage once.
// On solve: written to localStorage immediately + posted to Cloudflare.
// On unsolve: removed from localStorage immediately + posted to Cloudflare.
// Zero ongoing network/KV reads after the initial page load.
// ─────────────────────────────────────────────────────────────────

const LS_SOLVES_KEY = 'cv_solves';

/** Read the full solves map from localStorage */
function lsGetSolves() {
    try {
        return JSON.parse(localStorage.getItem(LS_SOLVES_KEY) || '{}');
    } catch (e) { return {}; }
}

/** Write the full solves map to localStorage */
function lsSaveSolves(map) {
    try { localStorage.setItem(LS_SOLVES_KEY, JSON.stringify(map)); } catch (e) {}
}

/** Apply a single solve into localStorage */
function lsSetSolve(courseId, updateObj) {
    const map = lsGetSolves();
    map[String(courseId)] = { update: updateObj, ts: Date.now() };
    lsSaveSolves(map);
}

/** Remove a single solve from localStorage */
function lsRemoveSolve(courseId) {
    const map = lsGetSolves();
    delete map[String(courseId)];
    lsSaveSolves(map);
}

/**
 * Merge Cloudflare solves into localStorage.
 * Called once at startup. Cloudflare is authoritative for solves the local
 * browser has never seen. Local is authoritative for anything newer.
 */
function mergeCloudflaresolves(pendingFromServer) {
    const local = lsGetSolves();
    let changed = false;
    for (const solve of (pendingFromServer || [])) {
        const id = String(solve.id);
        const serverTs = solve.ts || 0;
        const localTs = local[id] ? (local[id].ts || 0) : -1;
        // Only update if server has a newer entry than local
        if (localTs < serverTs) {
            const updateObj = solve.update && solve.update.$set ? solve.update.$set : solve.update;
            local[id] = { update: updateObj, ts: serverTs };
            changed = true;
        }
    }
    if (changed) lsSaveSolves(local);
}

/**
 * Apply all localStorage solves to the loaded course list.
 * Called once after courses are fetched.
 */
function applyLocalSolves(docs) {
    const map = lsGetSolves();
    for (const [id, entry] of Object.entries(map)) {
        if (!entry || !entry.update) continue;
        const c = docs.find(x => x.id == id);
        if (c) {
            const updateObj = entry.update.$set || entry.update;
            Object.assign(c, updateObj);
        }
    }
}

// No more polling — localStorage is the single source of truth for solves.
// pollSolves() and setInterval() removed entirely.



